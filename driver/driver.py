"""
Observation Monitoring Driver Script — single rolling window per run

This script runs EVA processing for multiple observation types using multiprocessing.
Each run:
    - Reads the current cycle endpoint from PDY (YYYYMMDD) and CYC (HH)
    - Builds one rolling window ending at that endpoint with exactly `CYCLES`
      timestamps spaced by `INTERVAL_HOURS`
    - For that window:
        - Finds matching NetCDF observation files
        - Copies them into a per-window runtime directory
        - Optionally creates stub .nc files for missing cycles
        - Generates a YAML config via Jinja
        - Runs EVA using that config
        - Optionally copies output plots to a public directory
    - Cleans up window/runtime data unless KEEP_DATA is set

Environment (set by Rocoto):
  PDY (YYYYMMDD), CYC (HH), INTERVAL_HOURS, CYCLES,
  RUN, RUNTIME_DIR, EXPDIR, DATAROOT, COMPONENT,
  CONFIG_YAML, COPY_DATA, KEEP_DATA, CREATE_STUBS, CDATE (for naming only).
"""

import os
import uuid
import shutil
import logging
import subprocess
import yaml
import re
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path
from multiprocessing import Pool, cpu_count

from wxflow import Logger, Jinja
from wxflow.configuration import cast_as_dtype
import wxflow

from yaml.generate_template import build_template_for_ob_type

from stubs import (
    clone_schema_stub,
    write_generic_stub,
    guess_domain_size,
)

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

class MonitoringConfig:
    """
    Encapsulates configuration for a single observation monitoring job.
    Uses PDY + CYC as the single cycle endpoint; window timestamps are
    derived from CYCLES and INTERVAL_HOURS.
    """

    def __init__(self, monitor_dict: dict, timestamp: str):
        self.monitor_type = monitor_dict['monitor_type']
        if self.monitor_type == 'radiance':
            self.satellite = monitor_dict["satellite"]
            self.sensor = monitor_dict["sensor"]
            self.ob_type = f"{self.sensor}_{self.satellite}"
        elif self.monitor_type == 'conventional':
            self.variable = monitor_dict["variable"]
            self.ob_type = f"{self.variable}"
        else:
            raise ValueError(f"Unknown monitor_type: {self.monitor_type}")

        # Template + naming
        # Template will be generated per-run via build_template_for_ob_type().
        self.template_path = None
        self.filename_template = monitor_dict.get("filename_template")

        # Component comes from the job definition (env is only used as a filter in main())
        self.component = monitor_dict.get("component")
        if not self.component:
            raise ValueError("Job missing 'component' key.")

        # ---- Timing: ONLY PDY + CYC (no SDATE/EDATE) ----
        pdy = os.getenv("PDY")
        cyc = os.getenv("CYC")
        if not pdy or not cyc:
            raise EnvironmentError("PDY and CYC must be set (PDY=YYYYMMDD, CYC=HH).")
        if not (pdy.isdigit() and len(pdy) == 8 and cyc.isdigit() and len(cyc) == 2):
            raise ValueError("PDY must be YYYYMMDD and CYC must be HH (zero-padded).")

        self.interval_hours = int(os.getenv("INTERVAL_HOURS"))
        if self.interval_hours <= 0:
            raise ValueError("INTERVAL_HOURS must be > 0")

        self.cycles = int(os.getenv("CYCLES"))  # number of timestamps per window (endpoint included)
        if self.cycles <= 0:
            raise ValueError("CYCLES must be > 0")

        # Current run endpoint; minutes=00; UTC
        self.end_time = datetime.strptime(pdy + cyc, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        # Convenience start_time (used as default in Jinja context)
        self.start_time = self.end_time - (self.cycles - 1) * timedelta(hours=self.interval_hours)

        # Paths
        self.timestamp = timestamp  # unique run label
        self.runtime_root = Path(os.getenv("RUNTIME_DIR"))
        # Job root (holds the single per-window subdir)
        self.runtime_dir = self.runtime_root / f"runtime_{self.ob_type}_{timestamp}_{uuid.uuid4().hex[:8]}"
        self.runtime_dir.mkdir(parents=True, exist_ok=False)

        self.experiment_dir = Path(os.getenv("EXPDIR"))
        self.dataroot = Path(os.getenv("DATAROOT"))
        self.comroot = Path(os.getenv("COMROOT"))
        self.run = Path(os.getenv("RUN"))

        # Optional ENV used elsewhere in your system
        self.pdy = Path(pdy)
        self.cyc = Path(cyc)

        # Flags
        self.copy_data = cast_as_dtype(os.getenv("COPY_DATA"))
        self.keep_data = cast_as_dtype(os.getenv("KEEP_DATA"))
        self.create_stubs = cast_as_dtype(os.getenv("CREATE_STUBS"))

    # ------------------------ context ------------------------

    def get_jinja_context(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        runtime_dir: Path | None = None,
    ):
        """
        Build the context dictionary passed to the Jinja template engine.
        Allows overriding start/end/runtime_dir for the window.
        """
        d = {
            "runtime_dir": str(runtime_dir or self.runtime_dir),
            "start_time": start_time or self.start_time,
            "end_time": end_time or self.end_time,
            "interval_hours": self.interval_hours,
            "ob_type": self.ob_type,
        }
        if self.monitor_type == 'radiance':
            d['satellite'] = self.satellite
            d['sensor'] = self.sensor
        elif self.monitor_type == 'conventional':
            d['variable'] = self.variable
    
        return d


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def extract_timestamp(file: Path) -> str | None:
    """
    Extract a timestamp string (10–14 digits) from the filename stem.

    Returns:
        str | None: The matched timestamp string if found, otherwise None.
    """
    match = re.search(r'\d{10,14}', file.stem)
    return match.group(0) if match else None


def infer_schema_from_template(cfg: MonitoringConfig) -> tuple[str, bool]:
    """
    Inspect the Jinja YAML template to infer (product_group, include_gridded_bins).
    Looks at lines under 'groups:' with 'name: <path>'.
    """
    pg = None
    include_gridded = False

    try:
        with open(cfg.template_path, "r") as tf:
            for line in tf:
                m = re.search(r"name:\s*([A-Za-z0-9_\/]+)", line)
                if not m:
                    continue
                path = m.group(1).strip()
                parts = path.split("/")
                if parts and parts[0] == "griddedBins":
                    include_gridded = True
                if len(parts) >= 1:
                    pg = parts[-1]
    except Exception:
        pass

    if not pg:
        ob = cfg.ob_type.lower()
        if "snow" in ob or "snocvr" in ob:
            pg = "totalSnowDepth"
        elif "aod" in ob or "viirs" in ob:
            pg = "aerosolOpticalDepth"
        else:
            pg = "value"

    return pg, include_gridded


def expected_stub_filename(cfg: MonitoringConfig, dt: datetime, reference_path: str | Path | None) -> str:
    """
    Use per-job filename_template when provided; else clone a reference name; else fallback.
    """
    ts = dt.strftime("%Y%m%d%H")
    if getattr(cfg, "filename_template", None):
        return dt.strftime(cfg.filename_template)
    if reference_path:
        ref_name = Path(reference_path).name
        return re.sub(r"\d{10,14}", ts, ref_name, count=1)

    return f"{cfg.ob_type}_{ts}.nc"


def create_stub_for_missing_cycle(
    cfg: MonitoringConfig,
    dt: datetime,
    logger,
    reference_path: str | Path | None = None,
    output_dir: Path | None = None
):
    """
    Create a stub .nc for a missing cycle into `output_dir` (defaults to cfg.runtime_dir).
    Tries cloning schema from a real file; falls back to a generic byDomains stub.
    """
    out_dir = output_dir or cfg.runtime_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = expected_stub_filename(cfg, dt, reference_path)
    out = out_dir / fname

    if reference_path:
        try:
            clone_schema_stub(reference_path, out, dt)
            logger.info(f"[{cfg.ob_type}] Stub cloned from real: {Path(reference_path).name} -> {out.name}")
            return True
        except Exception as e:
            logger.warning(f"[{cfg.ob_type}] Clone failed; falling back to generic stub: {e}")

    product_group, include_gridded = infer_schema_from_template(cfg)
    try:
        write_generic_stub(
            out_path=out,
            dt=dt,
            ob_type=cfg.ob_type,
            product_group=product_group,
            include_gridded_bins=include_gridded,
        )
        logger.info(f"[{cfg.ob_type}] Generic stub written: {out.name} (pg={product_group}, gridded={include_gridded})")
        return True
    except Exception as e:
        logger.error(f"[{cfg.ob_type}] Failed to write generic stub {out.name}: {e}")
        return False


def write_coverage_report(expected_times, found_times, out_path, logger):
    """
    Write a CSV coverage report for expected vs found times.
    Returns a human-readable coverage string, e.g., "3/4 (75%)".
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    found = {dt for dt in found_times}
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "present"])
        for t in expected_times:
            w.writerow([t.strftime("%Y-%m-%d %H:%M"), int(t in found)])
        cov_num = f"{len(found)}/{len(expected_times)}"
        cov_pct = f"{(len(found)/len(expected_times))*100:.0f}%" if expected_times else "n/a"
        w.writerow([])
        w.writerow(["coverage", cov_num])
        w.writerow(["coverage_pct", cov_pct])
    logger.info(f"[coverage] {cov_num} ({cov_pct}) -> {out_path}")

    return f"{cov_num} ({cov_pct})"


def build_expected_times_for_window(t_end: datetime, interval_hours: int, cycles: int) -> list[datetime]:
    """
    Build the expected timeline for the single window with exactly `cycles` timestamps,
    ending at `t_end`.

    Example: cycles=4, interval=6h -> 4 timestamps:
        [t_end-18h, t_end-12h, t_end-6h, t_end]
    """
    interval = timedelta(hours=interval_hours)
    t_start = t_end - (cycles - 1) * interval
    return [t_start + i * interval for i in range(cycles)]


def find_matching_nc_files_for_times(cfg: MonitoringConfig, expected_times: list[datetime], logger):
    """
    Scan DATAROOT for NetCDF files matching the given expected_times for one window.

    Returns:
        (nc_files, expected_times, found_times)
        List[Path], List[datetime], List[datetime]
    """
    nc_files = []
    found_times = []
    pattern = f"{cfg.ob_type}_*.nc"

    logger.info(
        f"[{cfg.ob_type}] Window search from {expected_times[0]} to {expected_times[-1]} "
        f"({len(expected_times)} timestamps)"
    )

    for dt in expected_times:
        pdy_str = dt.strftime("%Y%m%d")  # gdas.PDY directory
        cyc_str = dt.strftime("%H")      # CYC subdirectory
        run_dir = cfg.dataroot / f"{cfg.run}.{pdy_str}" / f"{cyc_str}/products/{cfg.component}/anlmon"

        if not run_dir.exists():
            logger.warning(f"Expected directory does not exist: {run_dir}")
            continue

        if getattr(cfg, "filename_template", None):
            expected_name = dt.strftime(cfg.filename_template)
            f = run_dir / expected_name
            if f.exists():
                nc_files.append(f)
                found_times.append(dt)
            else:
                logger.warning(f"Missing expected file {f}")
            continue

        matched_files = []
        for file in run_dir.glob(pattern):
            timestamp_str = extract_timestamp(file)
            if not timestamp_str:
                logger.debug(f"No timestamp found in {file.name}, skipping")
                continue

            # Match on cycle-hour (YYYYMMDDHH); minutes/seconds in names still ok
            file_cycle = timestamp_str[:10]
            if file_cycle == dt.strftime("%Y%m%d%H"):
                matched_files.append(file)

        if not matched_files:
            logger.warning(f"No files found for expected cycle {dt.strftime('%Y%m%d%H')} in {run_dir}")
        else:
            nc_files.extend(matched_files)
            found_times.append(dt)

    logger.info(f"Found {len(nc_files)} files for window ending {expected_times[-1]}")

    return sorted(nc_files), expected_times, found_times


def copy_nc_files_to_runtime(nc_files, cfg: MonitoringConfig, logger, dest_dir: Path):
    """
    Copy matched NetCDF files into `dest_dir`. Logs and continues on per-file errors.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for file in nc_files:
        try:
            shutil.copy2(file, dest_dir / file.name)
            copied += 1
            logger.info(f"[{cfg.ob_type}] Copied: {file.name}")
        except FileNotFoundError:
            logger.warning(f"[{cfg.ob_type}] Source vanished before copy: {file}")
        except PermissionError as e:
            logger.error(f"[{cfg.ob_type}] Permission error copying {file}: {e}")
        except Exception as e:
            logger.error(f"[{cfg.ob_type}] Unexpected error copying {file}: {e}")
    if copied == 0:
        logger.warning(f"[{cfg.ob_type}] No files were copied into {dest_dir}")


def generate_eva_config(cfg: MonitoringConfig, logger, runtime_dir: Path,
                        win_start: datetime, win_end: datetime) -> Path:
    """
    Generate an EVA YAML configuration for the window into `runtime_dir`.
    """
    context = cfg.get_jinja_context(start_time=win_start, end_time=win_end, runtime_dir=runtime_dir)
    output_path = runtime_dir / "eva_config.yaml"
    jinja = Jinja(template_path_or_string=cfg.template_path, data=context)
    jinja.save(output_file=output_path)
    logger.info(f"Generated EVA config: {output_path}")

    return output_path


def build_eva_template_for_job(cfg: MonitoringConfig, logger) -> Path:
    """
    Build a modular EVA YAML template for this ob_type and write it into the
    job's runtime root directory. Updates cfg.template_path and returns it.

    This is run once per job/run, so we avoid accumulating hundreds of static
    templates on disk across cycles.
    """
    # Build the modular template dict for this ob_type
    doc = build_template_for_ob_type(cfg.ob_type)

    # Write a per-job template file under the job root (ephemeral)
    template_path = cfg.runtime_dir / "eva_template.yaml.j2"
    template_path.parent.mkdir(parents=True, exist_ok=True)

    text = yaml.safe_dump(doc, sort_keys=False, width=1000)
    template_path.write_text(text)

    cfg.template_path = str(template_path)
    logger.info(f"[{cfg.ob_type}] Built modular EVA template: {template_path}")

    return template_path


def run_eva(cfg: MonitoringConfig, eva_config_path: Path, logger) -> tuple[bool, str | None]:
    """
    Execute EVA with the generated config file.

    Returns:
        (ok, err): ok=True on success; err contains an error string on failure.
    """
    eva_exe = wxflow.executable.which("eva")
    if not eva_exe:
        msg = "EVA executable not found in PATH."
        logger.error(f"[{cfg.ob_type}] {msg} Skipping EVA.")
        return False, msg

    try:
        cp = subprocess.run([str(eva_exe), str(eva_config_path)], check=True)
        logger.info(f"[{cfg.ob_type}] EVA completed successfully.")
        return True, None
    except subprocess.CalledProcessError as e:
        msg = f"EVA failed with code {e.returncode}"
        logger.error(f"[{cfg.ob_type}] {msg}. Continuing.")
        return False, msg
    except FileNotFoundError:
        msg = "EVA executable not found at runtime"
        logger.error(f"[{cfg.ob_type}] {msg}. Continuing.")
        return False, msg
    except Exception as e:
        msg = f"Unexpected EVA error: {e}"
        logger.error(f"[{cfg.ob_type}] {msg}. Continuing.")
        return False, msg


def com_plots_dir_for_window(cfg: MonitoringConfig, t_end: datetime) -> Path:
    """
    Build the COM destination directory for plots for this window, e.g.:
      <COMROOT>/<RUN>.<PDY>/<CYC>/<component>/
    """
    pdy = t_end.strftime("%Y%m%d")
    cyc = t_end.strftime("%H")
    return (
        cfg.comroot
        / f"{cfg.run}.{pdy}"
        / f"{cyc}"
        / cfg.component
    )


def copy_plots_to_com(cfg: MonitoringConfig, logger, source_dir: Path, t_end: datetime):
    """
    Copy the entire plots/ directory produced for this window into COM.
    This runs **every time**, regardless of COPY_DATA.
    """
    plots_dir = source_dir / "plots"
    if not plots_dir.exists():
        logger.warning(f"No plots/ directory found in {source_dir}; COM copy skipped.")
        return

    if not cfg.comroot:
        logger.warning("COMROOT not set; cannot copy plots to COM.")
        return

    dest_dir = com_plots_dir_for_window(cfg, t_end)
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Copy the tree (preserve substructure). Use copy2 per file to overwrite safely.
    copied = 0
    for src in plots_dir.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(plots_dir)
        out = dest_dir / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, out)
            copied += 1
        except Exception as e:
            logger.error(f"Failed copying {src} -> {out}: {e}")

    logger.info(f"Copied {copied} plot file(s) to COM: {dest_dir}")


def copy_plots_to_public(cfg: MonitoringConfig, logger, source_dir: Path,
                         public_root: Path = Path("/public") / "plots"):
    """
    Copy generated PNG plots from `source_dir/plots` to a public location.
    """
    plots_dir = source_dir / "plots"
    if not plots_dir.exists():
        logger.warning(f"No plots/ directory in {source_dir}")
        return

    for plot_file in plots_dir.rglob("*.png"):
        rel_path = plot_file.relative_to(plots_dir)
        target_path = public_root / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plot_file, target_path)
        logger.info(f"Copied plot to public: {target_path}")


def cleanup_path(path: Path, logger):
    """
    Delete a directory tree if it exists.
    """
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        logger.info(f"Deleted runtime dir: {path}")

# -----------------------------------------------------------------------------
# Job Execution (single window per run)
# -----------------------------------------------------------------------------

def run_monitoring_job(args):
    """
    For the current cycle endpoint (PDY+CYC), build a window of `CYCLES` timestamps,
    discover inputs, optionally stub missing, run EVA, copy plots, and clean up.
    """
    monitor_dict, timestamp = args
    cfg = MonitoringConfig(monitor_dict, timestamp)
    logger = Logger(f"Obs Monitor - {cfg.ob_type}")
    logger.info(f"Starting job for {cfg.ob_type}")

    # Build the modular EVA template for this ob_type for this run
    build_eva_template_for_job(cfg, logger)

    try:
        # Build the single window for this run
        t_end = cfg.end_time
        win_times = build_expected_times_for_window(
            t_end=t_end,
            interval_hours=cfg.interval_hours,
            cycles=cfg.cycles,
        )
        win_start = win_times[0]

        # Per-window runtime dir: <job-root>/<YYYYMMDDHHMM of endpoint>
        window_dir = cfg.runtime_dir / f"{t_end.strftime('%Y%m%d%H%M')}"
        window_dir.mkdir(parents=True, exist_ok=True)

        # Discover files for this window
        nc_files, expected_times, found_times = find_matching_nc_files_for_times(cfg, win_times, logger)
        cov_str = write_coverage_report(expected_times, found_times, window_dir / "coverage.csv", logger)

        # Choose a reference real file (if any) for schema cloning
        ref_path = nc_files[0] if nc_files else None

        # Optionally make stubs for missing cycles
        if cfg.create_stubs and expected_times:
            missing = [dt for dt in expected_times if dt not in set(found_times)]
            if missing:
                logger.info(f"[{cfg.ob_type}] Creating {len(missing)} stub files for missing cycles "
                            f"(window end {t_end:%Y-%m-%d %H:%M})")
                for dt in missing:
                    create_stub_for_missing_cycle(
                        cfg, dt, logger, reference_path=ref_path, output_dir=window_dir
                    )

        # Stage real files into the window dir
        copy_nc_files_to_runtime(nc_files, cfg, logger, dest_dir=window_dir)

        # If the window dir has no inputs at all, skip EVA for this window
        if not any(window_dir.glob("*.nc")):
            logger.warning(
                f"[{cfg.ob_type}] No inputs (.nc) in window dir {window_dir}. "
                f"Skipping EVA. Coverage: {cov_str}"
            )
            return {"ob_type": cfg.ob_type, "status": "skipped_no_input", "coverage": cov_str}

        # Generate and run EVA for this window
        eva_config_path = generate_eva_config(cfg, logger, runtime_dir=window_dir,
                                              win_start=win_start, win_end=t_end)
        ok_eva, err_eva = run_eva(cfg, eva_config_path, logger)

        # Always copy to COM (even if EVA failed, in case plots exist from partial work)
        copy_plots_to_com(cfg, logger, source_dir=window_dir, t_end=t_end)

        # Optional public copy
        if cfg.copy_data:
            copy_plots_to_public(cfg, logger, source_dir=window_dir)

        if ok_eva:
            return {"ob_type": cfg.ob_type, "status": "ok", "coverage": cov_str}
        else:
            return {"ob_type": cfg.ob_type, "status": "failed", "error": err_eva, "coverage": cov_str}

    finally:
        # Remove the job root dir if empty and not keeping data
        if not cfg.keep_data and cfg.runtime_dir.exists():
            try:
                if not any(cfg.runtime_dir.iterdir()):
                    shutil.rmtree(cfg.runtime_dir)
                    logger.info(f"Deleted job root dir: {cfg.runtime_dir}")
            except Exception as e:
                logger.warning(f"[{cfg.ob_type}] Cleanup issue on job root: {e}")
        else:
            logger.info(f"[{cfg.ob_type}] KEEP_DATA=True. Results kept under: {cfg.runtime_dir}")

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    """
    Parse job list from CONFIG_YAML and run monitoring jobs in parallel.
    Respects optional COMPONENT filter from the environment.
    """
    main_logger = Logger("Obs Monitor - main")

    # CDATE used only to generate a unique, stable timestamp label
    cdate = os.getenv("CDATE")
    if not cdate:
        # Fallback: derive from PDY+CYC
        pdy = os.getenv("PDY")
        cyc = os.getenv("CYC")
        if not (pdy and cyc):
            raise EnvironmentError("CDATE or both PDY and CYC must be set.")
        cdate = pdy + cyc
    try:
        timestamp = datetime.strptime(cdate, "%Y%m%d%H").strftime("%Y%m%d_%H%M%S")
    except ValueError:
        raise ValueError("CDATE must be in format YYYYMMDDHH (or set PDY+CYC so we can derive it).")

    config_yaml = os.getenv("CONFIG_YAML")
    if not config_yaml:
        raise EnvironmentError("CONFIG_YAML is not set")

    with open(config_yaml, "r") as f:
        config = yaml.safe_load(f)

    job_list = config["jobs"] if isinstance(config, dict) and "jobs" in config else config
    if not isinstance(job_list, list):
        job_list = [job_list]

    # Filter by COMPONENT env if present (can be comma-separated)
    component_filter = os.getenv("COMPONENT")
    if component_filter:
        requested_components = {c.strip() for c in component_filter.split(",")}
        original_count = len(job_list)
        job_list = [job for job in job_list if job.get("component") in requested_components]
        skipped = original_count - len(job_list)
        main_logger.info(
            f"Filtered jobs: running {len(job_list)} matching components "
            f"({', '.join(requested_components)}), skipped {skipped}."
        )

    if not job_list:
        main_logger.warning("No jobs match the given COMPONENT filter. Exiting ...")
        return

    job_args = [(job, timestamp) for job in job_list]
    nprocs = min(cpu_count(), len(job_args))
    main_logger.info(f"Starting multiprocessing with {nprocs} processes")

    with Pool(processes=nprocs) as pool:
        results = pool.map(run_monitoring_job, job_args)

    ok = sum(1 for r in results if r.get("status") == "ok")
    skipped = [r for r in results if r.get("status", "").startswith("skipped")]
    failed = [r for r in results if r.get("status") == "failed"]
    main_logger.info(f"Job summary: {ok} ok, {len(skipped)} skipped, {len(failed)} failed (non-fatal).")
    for r in skipped:
        main_logger.info(f"Skipped {r['ob_type']}: {r['status']} — coverage {r.get('coverage')}")
    for r in failed:
        main_logger.info(f"Failed {r['ob_type']}: {r.get('error')}")


if __name__ == "__main__":
    main()
