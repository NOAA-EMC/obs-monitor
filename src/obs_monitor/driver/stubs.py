# stubs.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional
import re

# ------------------------
# Constants
# ------------------------

# Fill value consistent with real obs-monitor NetCDF files
DEFAULT_FLOAT_FILL = -3.368795e+38

# Always write ISO UTC timestamps: e.g. 2025-01-31T18:00:00Z
VALIDTIME_STRFTIME = "%Y-%m-%dT%H:00:00Z"

# Hour offset applied between cycle time and validTime when no reference
# file is available to derive it from.
DEFAULT_VALIDTIME_OFFSET_HOURS = 3


# ------------------------
# Time helpers
# ------------------------

def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def _format_valid_iso(dt: datetime) -> str:
    return _utc(dt).strftime(VALIDTIME_STRFTIME)


def _extract_cycle_from_filename(name: str) -> Optional[datetime]:
    """
    Extract cycle timestamp from a filename by finding the first 10–14 digit run.
    Returns a UTC datetime or None.
    """
    m = re.search(r"(\d{10,14})", name)
    if not m:
        return None
    ts = m.group(1)
    try:
        if len(ts) == 10:
            return datetime.strptime(ts, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        if len(ts) == 12:
            return datetime.strptime(ts, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        if len(ts) == 14:
            return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _parse_valid_string(s: str) -> Optional[datetime]:
    """Parse several common validTime string styles to a UTC datetime."""
    if not s:
        return None
    s = s.strip()
    try:
        if s.endswith("Z") and "T" in s:
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if s.endswith("z") and " " in s:
            y, m, d, hh = s[:-1].split()
            return datetime(int(y), int(m), int(d), int(hh), tzinfo=timezone.utc)
        if "-" in s and ":" in s and "T" not in s:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if s.isdigit() and len(s) == 10:
            return datetime.strptime(s, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _valid_offset_hours_from_reference(ref_valid: Optional[str], ref_fname: str) -> int:
    """
    Compute (validTime - cycleTime) in whole hours from a reference file,
    based on the validTime string inside the file and the timestamp in the
    filename. Falls back to DEFAULT_VALIDTIME_OFFSET_HOURS if either cannot
    be parsed.
    """
    vdt = _parse_valid_string(ref_valid) if ref_valid else None
    fdt = _extract_cycle_from_filename(ref_fname)
    if not vdt or not fdt:
        return DEFAULT_VALIDTIME_OFFSET_HOURS
    delta = vdt - fdt
    return int(round(delta.total_seconds() / 3600.0))


# ------------------------
# Internal schema helpers
# ------------------------

def _collect_group_specs(figure_specs: list[dict]) -> dict[str, set[str]]:
    """
    Walk figure specs and collect the unique stat variables required under
    each group_path.

    Returns a dict mapping group_path -> set of stat variable names, e.g.::

        {
            "byDomains/ombg/stationPressure": {"assimilated_mean"},
            "byDomains/oman/stationPressure": {"assimilated_mean"},
            "griddedBins/ombg/stationPressure": {"assimilated_mean"},
            "griddedBins/oman/stationPressure": {"assimilated_mean"},
        }

    This is the minimal set that validate_nc_file will check, so it is
    exactly what write_generic_stub needs to create.
    """
    groups: dict[str, set[str]] = {}
    for spec in figure_specs:
        gp = spec.get("group_path", "")
        stat = spec.get("stat", "")
        if not gp or not stat:
            continue
        groups.setdefault(gp, set()).add(stat)
    return groups


def _ensure_group_path(root, group_path: str):
    """
    Walk or create every segment of a slash-separated group path under root,
    returning the deepest group.
    """
    current = root
    for segment in group_path.strip("/").split("/"):
        if segment in current.groups:
            current = current.groups[segment]
        else:
            current = current.createGroup(segment)
    return current


# ------------------------
# Public API
# ------------------------

def clone_schema_stub(ref_path: str | Path, out_path: str | Path, dt: datetime) -> str:
    """
    Clone dims/groups/vars/attrs from ref_path and write an empty stub at
    out_path for cycle dt.

    - validTime is always written in ISO UTC (YYYY-MM-DDTHH:00:00Z)
    - The hour offset between filename cycle and validTime is preserved from
      the reference file

    Requires: netCDF4, numpy
    """
    import numpy as np
    from netCDF4 import Dataset

    ref_path, out_path = Path(ref_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def copy_root_dims(src_root, dst_root):
        sizes = {}
        unlimited = set()
        for name, d in src_root.dimensions.items():
            if d.isunlimited():
                dst_root.createDimension(name, None)
                sizes[name] = None
                unlimited.add(name)
            else:
                dst_root.createDimension(name, len(d))
                sizes[name] = len(d)
        return sizes, unlimited

    def copy_attrs(src_obj, dst_obj):
        for att in getattr(src_obj, "ncattrs", lambda: [])():
            if att == "_FillValue":
                continue
            try:
                dst_obj.setncattr(att, src_obj.getncattr(att))
            except Exception:
                pass

    def create_var(src_var, dst_grp):
        kwargs = {}
        if src_var.ndim > 0:
            kwargs = dict(zlib=True, complevel=1)
        try:
            fv = src_var.getncattr("_FillValue")
        except Exception:
            fv = None

        if src_var.dtype == str or str(src_var.dtype) == "str":
            kind = "S"
        else:
            kind = src_var.dtype.kind

        if fv is not None and kind in ("f", "i", "u"):
            dst_var = dst_grp.createVariable(
                src_var.name, src_var.dtype, src_var.dimensions,
                fill_value=fv, **kwargs,
            )
        else:
            vtype = "str" if kind in ("S", "U", "O") else src_var.dtype
            dst_var = dst_grp.createVariable(
                src_var.name, vtype, src_var.dimensions, **kwargs,
            )
        copy_attrs(src_var, dst_var)
        return dst_var

    def write_empty(var, root_dim_sizes: dict, unlimited_names: set):
        shape = []
        for dname in var.dimensions:
            if dname in unlimited_names:
                shape.append(1)
            else:
                size = root_dim_sizes.get(dname)
                if size is None:
                    size = 1
                shape.append(size)

        if var.dtype == str or str(var.dtype) == "str":
            kind = "S"
        else:
            kind = var.dtype.kind

        if kind == "f":
            var[:] = np.nan
        elif kind in ("i", "u"):
            var[:] = 0
        else:
            arr = np.empty(shape, dtype=object)
            arr.fill("NA")
            var[:] = arr

    def read_ref_validtime_str(grp) -> Optional[str]:
        for name, v in grp.variables.items():
            if name.lower() == "validtime":
                try:
                    val = v[0]
                    if hasattr(val, "tobytes"):
                        val = val.tobytes().decode("utf-8", "ignore")
                    if isinstance(val, bytes):
                        val = val.decode("utf-8", "ignore")
                    return str(val)
                except Exception:
                    return None
        return None

    def specialize_valid_time(dst_grp, cycle_dt: datetime, offset_hours: int):
        for name, v in dst_grp.variables.items():
            if (
                name.lower() == "validtime" \
                and v.ndim == 1 \
                and v.dimensions[0].lower() == "analysiscycle"
            ):
                target = _utc(cycle_dt) + timedelta(hours=offset_hours)
                v[0] = _format_valid_iso(target)

    def walk(src_grp, dst_grp, root_dim_sizes, unlimited_names, offset_hours):
        for _, src_var in src_grp.variables.items():
            dst_var = create_var(src_var, dst_grp)
            write_empty(dst_var, root_dim_sizes, unlimited_names)
        specialize_valid_time(dst_grp, dt, offset_hours)
        copy_attrs(src_grp, dst_grp)
        for gname, src_sub in src_grp.groups.items():
            walk(src_sub, dst_grp.createGroup(gname), root_dim_sizes, unlimited_names, offset_hours)

    with Dataset(ref_path, "r") as src, Dataset(out_path, "w", format="NETCDF4") as dst:
        ref_vstr = read_ref_validtime_str(src)
        offset_hours = _valid_offset_hours_from_reference(ref_vstr, ref_path.name)
        root_sizes, unlimited = copy_root_dims(src, dst)
        copy_attrs(src, dst)
        walk(src, dst, root_sizes, unlimited, offset_hours)

    return str(out_path)


def write_generic_stub(
    out_path: str | Path,
    dt: datetime,
    ob_type: str,
    plot_config: dict,
) -> str:
    """
    Write a minimal stub NetCDF file whose structure satisfies
    ``validate_nc_file`` for the given plot config.

    This is a last-resort fallback used only when no real reference file
    exists to clone from (i.e. the entire window has no data). The stub
    contains the correct group hierarchy and variable names with NaN/zero
    fill values so that the plotting pipeline can run and produce figures
    that show gaps at missing cycles rather than crashing.

    The group hierarchy, variable names, and dimension sizes are all derived
    from the plot config rather than hardcoded, so the stub schema
    automatically stays in sync with the YAML as new ob_types are onboarded.

    Parameters
    ----------
    out_path:
        Destination path for the stub file.
    dt:
        Cycle datetime (UTC). Used to set validTime and name the file.
    ob_type:
        Observation type string (used for the statisticDomain placeholder
        values and log context only — not for schema decisions).
    plot_config:
        The per-ob-type plot config dict loaded from the monitor type YAML.
        Must contain:
          - ``figures``: list of figure spec dicts, each with ``group_path``
            and ``stat`` keys
          - ``domain_count``: int, size of the Domain dimension
          - ``nc_groups.coords``: top-level coords group name (e.g.
            ``"griddedBins"``)
          - ``nc_groups.bins`` (optional): [binsZDim, binsYDim, binsXDim]
            for ob_types that have a griddedBins group; omit or null if not
            applicable

    Returns
    -------
    str
        Absolute path of the written stub file.

    Raises
    ------
    ValueError
        If ``plot_config`` is missing required keys (``figures``,
        ``domain_count``).
    """
    import numpy as np
    from netCDF4 import Dataset

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # --- Validate required config keys ---
    figure_specs = plot_config.get("figures")
    if not figure_specs:
        raise ValueError(
            f"[{ob_type}] plot_config missing 'figures' key — "
            "cannot derive stub schema."
        )
    domain_count = plot_config.get("domain_count")
    if not domain_count:
        raise ValueError(
            f"[{ob_type}] plot_config missing 'domain_count' key — "
            "cannot size Domain dimension for stub."
        )

    nc_groups = plot_config.get("nc_groups", {})
    coords_group = nc_groups.get("coords", "")
    bins = nc_groups.get("bins")          # [binsZDim, binsYDim, binsXDim] or None

    # --- Derive the group/variable schema from figure specs ---
    # Maps group_path -> set of stat variable names that must exist there.
    # This is exactly what validate_nc_file checks, nothing more.
    group_specs = _collect_group_specs(figure_specs)

    # --- Compute validTime ---
    vtime_str = _format_valid_iso(
        _utc(dt) + timedelta(hours=DEFAULT_VALIDTIME_OFFSET_HOURS)
    )

    FILL_F = np.float32(DEFAULT_FLOAT_FILL)

    with Dataset(out_path, "w", format="NETCDF4") as nc:

        # --- Root dimensions ---
        nc.createDimension("analysisCycle", None)   # unlimited
        nc.createDimension("Domain", domain_count)
        if bins:
            bz, by, bx = bins
            nc.createDimension("binsZDim", bz)
            nc.createDimension("binsYDim", by)
            nc.createDimension("binsXDim", bx)

        # --- Root variables ---
        vt = nc.createVariable("validTime", str, ("analysisCycle",))
        vt[0] = vtime_str

        sd = nc.createVariable("statisticDomain", str, ("Domain",))
        sd[:] = np.array(
            [f"D{i:02d}" for i in range(1, domain_count + 1)], dtype=object
        )

        if bins:
            vb = nc.createVariable("verticalBin", str, ("binsZDim",))
            vb[:] = np.array(["L01"], dtype=object)

        # --- coords group (griddedBins with lat/lon placeholders) ---
        # validate_nc_file checks that this group exists; read_coords also
        # expects latitude/longitude variables within it.
        if coords_group:
            cg = nc.createGroup(coords_group)
            if bins:
                by_size = bins[1]
                bx_size = bins[2]
                lat = cg.createVariable(
                    "latitude", "f4", ("binsYDim", "binsXDim"),
                    zlib=True, complevel=1,
                )
                lat.units = "degrees_north"
                lat.long_name = "latitude of bin centers"
                lat[:] = np.full((by_size, bx_size), np.nan, dtype=np.float32)

                lon = cg.createVariable(
                    "longitude", "f4", ("binsYDim", "binsXDim"),
                    zlib=True, complevel=1,
                )
                lon.units = "degrees_east"
                lon.long_name = "longitude of bin centers"
                lon[:] = np.full((by_size, bx_size), np.nan, dtype=np.float32)

        # --- Data groups derived from figure specs ---
        for group_path, stat_vars in group_specs.items():
            # Determine which root-level group this path falls under so we
            # know which dimensions to use.
            top_level = group_path.strip("/").split("/")[0]
            use_bins = bins and top_level == coords_group

            grp = _ensure_group_path(nc, group_path)

            for stat in stat_vars:
                if use_bins:
                    dims = ("analysisCycle", "binsZDim", "binsYDim", "binsXDim")
                    var = grp.createVariable(
                        stat, "f4", dims,
                        zlib=True, complevel=1, fill_value=FILL_F,
                    )
                    var[:] = np.nan
                else:
                    dims = ("analysisCycle", "Domain")
                    var = grp.createVariable(
                        stat, "f4", dims,
                        zlib=True, complevel=1, fill_value=FILL_F,
                    )
                    var[:] = np.nan

    return str(out_path)


__all__ = [
    "DEFAULT_FLOAT_FILL",
    "clone_schema_stub",
    "write_generic_stub",
]
