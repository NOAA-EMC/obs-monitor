"""
Observation Monitoring Driver Script — single rolling window per run

This script runs plotting for multiple observation types using multiprocessing.
Each run:
- Reads the current cycle endpoint from PDY (YYYYMMDD) and CYC (HH)
- Builds one rolling window ending at that endpoint with exactly `CYCLES`
timestamps spaced by `INTERVAL_HOURS`
- For that window:
  - Finds matching NetCDF observation files
  - Copies them into a per-window runtime directory
  - Optionally creates stub .nc files for missing cycles
  - Runs the internal plotting pipeline (obs_monitor.plotting)
  - Copies output plots to COM
  - Optionally copies output plots to a public directory
  - Cleans up window/runtime data unless KEEP_DATA is set

Environment (set by Rocoto):
PDY (YYYYMMDD), CYC (HH), INTERVAL_HOURS, CYCLES,
RUN, RUNTIME_DIR, EXPDIR, DATAROOT, COMPONENT,
CONFIG_YAML, PLOT_CONFIG_YAML, COPY_DATA, KEEP_DATA, CREATE_STUBS,
CDATE (for naming only).

"""

import os
import uuid
import shutil
import logging
import yaml
import re
import csv
import tarfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from multiprocessing import Pool, cpu_count

from wxflow import Logger
from wxflow.configuration import cast_as_dtype

from obs_monitor import build_template_for_ob_type
from obs_monitor.plotting import dispatch_plots

from .stubs import (
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
            self.sensor    = monitor_dict["sensor"]
            self.ob_type   = f"{self.sensor}_{self.satellite}"
        elif self.monitor_type == 'conventional':
            self.variable = monitor_dict["variable"]
            self.ob_type  = f"{self.variable}"
        else:
            raise ValueError(f"Unknown monitor_type: {self.monitor_type}")

        self.filename_template = monitor_dict.get("filename_template")

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

        self.cycles = int(os.getenv("CYCLES"))
        if self.cycles <= 0:
            raise ValueError("CYCLES must be > 0")

        self.end_time   = datetime.strptime(pdy + cyc, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        self.start_time = self.end_time - (self.cycles - 1) * timedelta(hours=self.interval_hours)

        # Paths
        self.timestamp    = timestamp
        self.runtime_root = Path(os.getenv("RUNTIME_DIR"))
        self.runtime_dir  = (
            self.runtime_root
            / f"runtime_{self.ob_type}_{timestamp}_{uuid.uuid4().hex[:8]}"
        )
        self.runtime_dir.mkdir(parents=True, exist_ok=False)

        self.experiment_dir = Path(os.getenv("EXPDIR"))
        self.dataroot       = Path(os.getenv("DATAROOT"))
        self.comroot        = Path(os.getenv("COMROOT"))
        self.run            = Path(os.getenv("RUN"))
        self.pdy            = Path(pdy)
        self.cyc            = Path(cyc)

        # Flags
        self.copy_data    = cast_as_dtype(os.getenv("COPY_DATA"))
        self.keep_data    = cast_as_dtype(os.getenv("KEEP_DATA"))
        self.create_stubs = cast_as_dtype(os.getenv("CREATE_STUBS"))


# -----------------------------------------------------------------------------
# Helpers  (all unchanged from original)
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
    """
    pg = None
    include_gridded = False
    try:
        with open(cfg.template_path, "r") as tf:
            for line in tf:
                m = re.search(r"name:\s*([A-Za-z0-9_\/]+)", line)
                if not m:
                    continue
                path  = m.group(1).strip()
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


def expected_stub_filename(
    cfg: MonitoringConfig,
    dt: datetime,
    reference_path: str | Path | None,
) -> str:
    """
    Use per-job filename_template when provided; else clone a reference name;
    else fallback.
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
    output_dir: Path | None = None,
):
    """
    Create a stub .nc for a missing cycle into `output_dir`
    (defaults to cfg.runtime_dir).
    """
    out_dir = output_dir or cfg.runtime_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = expected_stub_filename(cfg, dt, reference_path)
    out   = out_dir / fname

    if reference_path:
        try:
            clone_schema_stub(reference_path, out, dt)
            logger.info(
                f"[{cfg.ob_type}] Stub cloned from real: "
                f"{Path(reference_path).name} -> {out.name}"
            )
            return True
        except Exception as e:
            logger.warning(
                f"[{cfg.ob_type}] Clone failed; falling back to generic stub: {e}"
            )

    product_group, include_gridded = infer_schema_from_template(cfg)
    try:
        write_generic_stub(
            out_path=out,
            dt=dt,
            ob_type=cfg.ob_type,
            product_group=product_group,
            include_gridded_bins=include_gridded,
        )
        logger.info(
            f"[{cfg.ob_type}] Generic stub written: {out.name} "
            f"(pg={product_group}, gridded={include_gridded})"
        )
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
        cov_pct = (
            f"{(len(found)/len(expected_times))*100:.0f}%"
            if expected_times else "n/a"
        )
        w.writerow([])
        w.writerow(["coverage", cov_num])
        w.writerow(["coverage_pct", cov_pct])

    logger.info(f"[coverage] {cov_num} ({cov_pct}) -> {out_path}")
    return f"{cov_num} ({cov_pct})"


def build_expected_times_for_window(
    t_end: datetime,
    interval_hours: int,
    cycles: int,
) -> list[datetime]:
    """
    Build the expected timeline for the single window with exactly `cycles`
    timestamps, ending at `t_end`.
    """
    interval  = timedelta(hours=interval_hours)
    t_start   = t_end - (cycles - 1) * interval
    return [t_start + i * interval for i in range(cycles)]


def find_matching_inputs_for_times(
    cfg: MonitoringConfig,
    expected_times: list[datetime],
    logger,
    window_dir: Path,
):
    """
    Scan DATAROOT for tarball files matching the given expected_times.
    Returns: (tarballs, expected_times, found_times)
    """
    tarballs_in_runtime = []
    found_times         = []

    logger.info(
        f"[{cfg.ob_type}] Window search (tarballs) from {expected_times[0]} "
        f"to {expected_times[-1]} ({len(expected_times)} timestamps)"
    )
    window_dir.mkdir(parents=True, exist_ok=True)

    for dt in expected_times:
        pdy_str  = dt.strftime("%Y%m%d")
        cyc_str  = dt.strftime("%H")
        run_dir  = (
            cfg.dataroot
            / f"{cfg.run}.{pdy_str}"
            / f"{cyc_str}/products/{cfg.component}/anlmon"
        )

        if not run_dir.exists():
            logger.warning(f"Expected directory does not exist: {run_dir}")
            continue

        archive_name = (
            f"gdas.t{cyc_str}z.{cfg.component}_analysis.ioda_hofx_stats.tar.gz"
        )
        archive_path = run_dir / archive_name

        if archive_path.exists():
            logger.info(
                f"[{cfg.ob_type}] Found tarball for expected cycle "
                f"{dt.strftime('%Y%m%d%H')}: {archive_path}"
            )
            try:
                time_prefix  = dt.strftime("%Y%m%d%H")
                dest_filename = f"{time_prefix}_{archive_path.name}"
                dest_archive  = window_dir / dest_filename
                shutil.copy2(archive_path, dest_archive)
                logger.info(
                    f"[{cfg.ob_type}] Copied tarball to runtime: "
                    f"{archive_path} -> {dest_archive}"
                )
                tarballs_in_runtime.append(dest_archive)
                found_times.append(dt)
            except Exception as e:
                logger.error(
                    f"[{cfg.ob_type}] Failed to copy tarball "
                    f"{archive_path} to {window_dir}: {e}"
                )
        else:
            logger.warning(
                f"[{cfg.ob_type}] No tarball found for expected cycle "
                f"{dt.strftime('%Y%m%d%H')} in {run_dir}"
            )

    logger.info(
        f"[{cfg.ob_type}] Staged {len(tarballs_in_runtime)} tarball(s) into "
        f"runtime for window ending {expected_times[-1]}"
    )
    return sorted(tarballs_in_runtime), expected_times, found_times


def extract_tarballs_and_find_nc_for_times(
    cfg: MonitoringConfig,
    tarballs_in_runtime: list[Path],
    expected_times: list[datetime],
    logger,
    window_dir: Path,
):
    """
    In the runtime directory:
    - Extract all tarballs.
    - Remove tarballs after extraction.
    - Remove .nc files that do not belong to this ob_type.
    - Scan for .nc files for each expected cycle.
    Returns: (nc_files, expected_times, found_times_nc)
    """
    # 1) Extract
    for tar_path in tarballs_in_runtime:
        try:
            logger.info(f"[{cfg.ob_type}] Extracting tarball in runtime: {tar_path}")
            with tarfile.open(tar_path, "r:gz") as tar:
                tar.extractall(path=window_dir)
        except Exception as e:
            logger.error(f"[{cfg.ob_type}] Failed to extract {tar_path}: {e}")

    # 1b) Remove tarballs after extraction
    for tar_path in tarballs_in_runtime:
        try:
            tar_path.unlink()
            logger.info(f"[{cfg.ob_type}] Removed tarball from runtime: {tar_path.name}")
        except Exception as e:
            logger.warning(
                f"[{cfg.ob_type}] Could not remove tarball {tar_path.name}: {e}"
            )

    # 1c) Remove unrelated NetCDF files
    keep_prefix = f"{cfg.ob_type}_"
    removed = 0
    for nc in window_dir.glob("*.nc"):
        if not nc.name.startswith(keep_prefix):
            try:
                nc.unlink()
                removed += 1
            except Exception as e:
                logger.warning(
                    f"[{cfg.ob_type}] Failed to remove unrelated file {nc.name}: {e}"
                )
    if removed:
        logger.info(
            f"[{cfg.ob_type}] Removed {removed} unrelated .nc file(s) from runtime dir"
        )

    # 2) Scan for .nc files per expected cycle
    nc_files   = []
    found_times = []
    pattern    = f"{cfg.ob_type}_*.nc"

    logger.info(
        f"[{cfg.ob_type}] Runtime search for .nc files from "
        f"{expected_times[0]} to {expected_times[-1]} "
        f"({len(expected_times)} timestamps) in {window_dir}"
    )

    for dt in expected_times:
        matched_files = []
        for file in window_dir.glob(pattern):
            timestamp_str = extract_timestamp(file)
            if not timestamp_str:
                logger.debug(f"No timestamp found in {file.name}, skipping")
                continue
            file_cycle = timestamp_str[:10]
            if file_cycle == dt.strftime("%Y%m%d%H"):
                matched_files.append(file)

        if not matched_files:
            logger.warning(
                f"[{cfg.ob_type}] No .nc files found for expected cycle "
                f"{dt.strftime('%Y%m%d%H')} in {window_dir}"
            )
        else:
            nc_files.extend(matched_files)
            found_times.append(dt)

    logger.info(
        f"[{cfg.ob_type}] Found {len(nc_files)} .nc file(s) in runtime "
        f"for window ending {expected_times[-1]}"
    )
    return sorted(nc_files), expected_times, found_times


def com_plots_dir_for_window(cfg: MonitoringConfig, t_end: datetime) -> Path:
    """
    Build the COM destination directory for plots for this window.
    """
    pdy = t_end.strftime("%Y%m%d")
    cyc = t_end.strftime("%H")
    return cfg.comroot / f"{cfg.run}.{pdy}" / f"{cyc}" / cfg.component


def copy_plots_to_com(
    cfg: MonitoringConfig,
    logger,
    source_dir: Path,
    t_end: datetime,
):
    """
    Copy the entire plots/ directory produced for this window into COM.
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


def copy_plots_to_public(
    cfg: MonitoringConfig,
    logger,
    source_dir: Path,
    public_root: Path = Path("/public") / "plots",
):
    """
    Copy generated PNG plots from `source_dir/plots` to a public location.
    """
    plots_dir = source_dir / "plots"
    if not plots_dir.exists():
        logger.warning(f"No plots/ directory in {source_dir}")
        return

    for plot_file in plots_dir.rglob("*.png"):
        rel_path    = plot_file.relative_to(plots_dir)
        target_path = public_root / rel_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plot_file, target_path)
        logger.info(f"Copied plot to public: {target_path}")


def cleanup_path(path: Path, logger):
    """Delete a directory tree if it exists."""
    if path.exists() and path.is_dir():
        shutil.rmtree(path)
        logger.info(f"Deleted runtime dir: {path}")


# -----------------------------------------------------------------------------
# Plot config loader
# -----------------------------------------------------------------------------

def load_plot_config(plot_config_yaml: str | Path, ob_type: str) -> dict | None:
    """
    Load the per-ob-type plotting config from the new YAML file.

    The YAML is keyed by ob_type at the top level::

        prepbufr_adpsfc:
          variable: stationPressure
          ...

    Parameters
    ----------
    plot_config_yaml:
        Path to the plotting config YAML (set via ``PLOT_CONFIG_YAML`` env).
    ob_type:
        The observation type key to look up.

    Returns
    -------
    dict | None
        The per-ob-type config dict, or ``None`` if the key is absent (with
        a WARNING logged).  A missing key is treated as "no plots configured"
        rather than an error so that new ob types can be onboarded to the
        pipeline before their plot config is written.
    """
    path = Path(plot_config_yaml)
    if not path.exists():
        logging.getLogger(__name__).error(
            "PLOT_CONFIG_YAML '%s' does not exist.", path
        )
        return None

    with open(path, "r") as f:
        full_config = yaml.safe_load(f)

    if not isinstance(full_config, dict):
        logging.getLogger(__name__).error(
            "PLOT_CONFIG_YAML '%s' did not parse to a dict.", path
        )
        return None

    cfg = full_config.get(ob_type)
    if cfg is None:
        logging.getLogger(__name__).warning(
            "ob_type '%s' not found in PLOT_CONFIG_YAML '%s'; "
            "no plots will be generated for this type.",
            ob_type, path,
        )
    return cfg


# -----------------------------------------------------------------------------
# Job Execution (single window per run)
# -----------------------------------------------------------------------------

def run_monitoring_job(args):
    """
    For the current cycle endpoint (PDY+CYC), build a window of `CYCLES`
    timestamps, discover inputs, optionally stub missing, run the internal
    plotting pipeline, copy plots, and clean up.
    """
    monitor_dict, timestamp = args
    cfg    = MonitoringConfig(monitor_dict, timestamp)
    logger = Logger(f"Obs Monitor - {cfg.ob_type}")
    logger.info(f"Starting job for {cfg.ob_type}")

    try:
        t_end    = cfg.end_time
        win_times = build_expected_times_for_window(
            t_end=t_end,
            interval_hours=cfg.interval_hours,
            cycles=cfg.cycles,
        )
        win_start = win_times[0]

        window_dir = cfg.runtime_dir / f"{t_end.strftime('%Y%m%d%H%M')}"
        window_dir.mkdir(parents=True, exist_ok=True)

        # 1) Discover tarballs in DATAROOT and copy them into runtime
        tarballs_in_runtime, expected_times, found_tarball_times = (
            find_matching_inputs_for_times(cfg, win_times, logger, window_dir=window_dir)
        )

        # 2) Extract tarballs and discover actual .nc files per cycle
        nc_files, _, found_times = extract_tarballs_and_find_nc_for_times(
            cfg,
            tarballs_in_runtime=tarballs_in_runtime,
            expected_times=expected_times,
            logger=logger,
            window_dir=window_dir,
        )

        # 3) Write coverage report based on real .nc presence
        cov_str = write_coverage_report(
            expected_times, found_times, window_dir / "coverage.csv", logger
        )

        ref_path = nc_files[0] if nc_files else None

        # 4) Optionally make stubs for missing cycles
        if cfg.create_stubs and expected_times:
            missing = [dt for dt in expected_times if dt not in set(found_times)]
            if missing:
                logger.info(
                    f"[{cfg.ob_type}] Creating {len(missing)} stub files for "
                    f"missing cycles (window end {t_end:%Y-%m-%d %H:%M})"
                )
                for dt in missing:
                    create_stub_for_missing_cycle(
                        cfg, dt, logger,
                        reference_path=ref_path,
                        output_dir=window_dir,
                    )

        # 5) Skip if no inputs at all
        if not any(window_dir.glob("*.nc")):
            logger.warning(
                f"[{cfg.ob_type}] No inputs (.nc) in window dir {window_dir}. "
                f"Skipping plots. Coverage: {cov_str}"
            )
            return {"ob_type": cfg.ob_type, "status": "skipped_no_input", "coverage": cov_str}

        # 6) Load plot config for this ob_type
        plot_config_yaml = os.getenv("PLOT_CONFIG_YAML")
        if not plot_config_yaml:
            logger.error(
                f"[{cfg.ob_type}] PLOT_CONFIG_YAML is not set; cannot generate plots."
            )
            return {"ob_type": cfg.ob_type, "status": "failed",
                    "error": "PLOT_CONFIG_YAML not set", "coverage": cov_str}

        ob_plot_config = load_plot_config(plot_config_yaml, cfg.ob_type)
        if ob_plot_config is None:
            # Warning already logged inside load_plot_config
            return {"ob_type": cfg.ob_type, "status": "skipped_no_plot_config",
                    "coverage": cov_str}

        # 7) Run the internal plotting pipeline
        plot_result = dispatch_plots(
            ob_type=cfg.ob_type,
            runtime_dir=window_dir,
            plot_config=ob_plot_config,
            output_dir=window_dir / "plots",
        )
        logger.info(
            f"[{cfg.ob_type}] Plots: "
            f"{plot_result['figures_written']}/{plot_result['figures_requested']} written, "
            f"status='{plot_result['status']}'"
        )
        if plot_result["errors"]:
            for err in plot_result["errors"]:
                logger.warning(f"[{cfg.ob_type}] Plot warning: {err}")

        # 8) Copy to COM (always, even on partial success — mirrors original behaviour)
        copy_plots_to_com(cfg, logger, source_dir=window_dir, t_end=t_end)

        # 9) Optional public copy
        if cfg.copy_data:
            copy_plots_to_public(cfg, logger, source_dir=window_dir)

        # Map dispatcher status onto driver status for the summary
        if plot_result["status"] == "ok":
            return {"ob_type": cfg.ob_type, "status": "ok", "coverage": cov_str}
        elif plot_result["status"] == "partial":
            return {"ob_type": cfg.ob_type, "status": "ok", "coverage": cov_str,
                    "warnings": plot_result["errors"]}
        else:
            return {"ob_type": cfg.ob_type, "status": "failed",
                    "error": "; ".join(plot_result["errors"]), "coverage": cov_str}

    finally:
        if not cfg.keep_data and cfg.runtime_dir.exists():
            try:
                if not any(cfg.runtime_dir.iterdir()):
                    shutil.rmtree(cfg.runtime_dir)
                    logger.info(f"Deleted job root dir: {cfg.runtime_dir}")
            except Exception as e:
                logger.warning(f"[{cfg.ob_type}] Cleanup issue on job root: {e}")
        else:
            logger.info(
                f"[{cfg.ob_type}] KEEP_DATA=True. Results kept under: {cfg.runtime_dir}"
            )


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main():
    """
    Parse job list from CONFIG_YAML and run monitoring jobs in parallel.
    Respects optional COMPONENT filter from the environment.
    """
    main_logger = Logger("Obs Monitor - main")

    cdate = os.getenv("CDATE")
    if not cdate:
        pdy = os.getenv("PDY")
        cyc = os.getenv("CYC")
        if not (pdy and cyc):
            raise EnvironmentError("CDATE or both PDY and CYC must be set.")
        cdate = pdy + cyc

    try:
        timestamp = datetime.strptime(cdate, "%Y%m%d%H").strftime("%Y%m%d_%H%M%S")
    except ValueError:
        raise ValueError(
            "CDATE must be in format YYYYMMDDHH (or set PDY+CYC so we can derive it)."
        )

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
        original_count       = len(job_list)
        job_list = [job for job in job_list if job.get("component") in requested_components]
        skipped  = original_count - len(job_list)
        main_logger.info(
            f"Filtered jobs: running {len(job_list)} matching components "
            f"({', '.join(requested_components)}), skipped {skipped}."
        )

    if not job_list:
        main_logger.warning("No jobs match the given COMPONENT filter. Exiting ...")
        return

    job_args = [(job, timestamp) for job in job_list]
    nprocs   = min(cpu_count(), len(job_args))
    main_logger.info(f"Starting multiprocessing with {nprocs} processes")

    with Pool(processes=nprocs) as pool:
        results = pool.map(run_monitoring_job, job_args)

    ok      = sum(1 for r in results if r.get("status") == "ok")
    skipped = [r for r in results if r.get("status", "").startswith("skipped")]
    failed  = [r for r in results if r.get("status") == "failed"]

    main_logger.info(
        f"Job summary: {ok} ok, {len(skipped)} skipped, {len(failed)} failed (non-fatal)."
    )
    for r in skipped:
        main_logger.info(f"Skipped {r['ob_type']}: {r['status']} — coverage {r.get('coverage')}")
    for r in failed:
        main_logger.info(f"Failed {r['ob_type']}: {r.get('error')}")


if __name__ == "__main__":
    main()
