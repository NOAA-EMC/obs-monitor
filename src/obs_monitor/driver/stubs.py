# stubs.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
import os
import re

# ------------------------
# Constants
# ------------------------

# Fill value consistent with your real files
DEFAULT_FLOAT_FILL = -3.368795e38

# Always write ISO UTC: e.g., 2025-01-31T18:00:00Z
VALIDTIME_STRFTIME = "%Y-%m-%dT%H:00:00Z"

# When no reference file exists, use this hour offset between cycle time and validTime.
# If your product is always +3h (like many snow stats), set this to 3.
DEFAULT_VALIDTIME_OFFSET_HOURS = 3

# If you want per-ob_type defaults, you can uncomment and use this mapping:
# DEFAULT_OFFSET_BY_OBTYPE = {
#     "snocvr": 3,
#     "viirs_n20": 0,
#     "viirs_npp": 0,
# }


# ------------------------
# Time helpers
# ------------------------

def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)


def _format_valid_iso(dt: datetime) -> str:
    return _utc(dt).strftime(VALIDTIME_STRFTIME)


def _extract_cycle_from_filename(name: str) -> Optional[datetime]:
    """
    Extract cycle timestamp from a filename by finding the first 10-14 digit run.
    Returns UTC datetime or None.
    """
    m = re.search(r"(\d{10,14})", name)
    if not m:
        return None
    ts = m.group(1)
    try:
        if len(ts) == 10:   # YYYYMMDDHH
            return datetime.strptime(ts, "%Y%m%d%H").replace(tzinfo=timezone.utc)
        if len(ts) == 12:   # YYYYMMDDHHMM
            return datetime.strptime(ts, "%Y%m%d%H%M").replace(tzinfo=timezone.utc)
        if len(ts) == 14:   # YYYYMMDDHHMMSS
            return datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _parse_valid_string(s: str) -> Optional[datetime]:
    """Parse several common validTime string styles -> UTC datetime."""
    if not s:
        return None
    s = s.strip()
    try:
        if s.endswith("Z") and "T" in s:
            # 2025-01-31T15:00:00Z
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if s.endswith("z") and " " in s:
            # 2025 01 31 18z
            y, m, d, hh = s[:-1].split()
            return datetime(int(y), int(m), int(d), int(hh), tzinfo=timezone.utc)
        if "-" in s and ":" in s and "T" not in s:
            # 2025-01-31 18:00:00
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        if s.isdigit() and len(s) == 10:
            # 2025013118
            return datetime.strptime(s, "%Y%m%d%H").replace(tzinfo=timezone.utc)
    except Exception:
        return None
    return None


def _valid_offset_hours_from_reference(ref_valid: Optional[str], ref_fname: str) -> int:
    """
    Compute (validTime - cycleTime) in whole hours from a reference file,
    based on the validTime string inside the file and the timestamp in the filename.
    Falls back to DEFAULT_VALIDTIME_OFFSET_HOURS if either cannot be parsed.
    """
    vdt = _parse_valid_string(ref_valid) if ref_valid else None
    fdt = _extract_cycle_from_filename(ref_fname)
    if not vdt or not fdt:
        return DEFAULT_VALIDTIME_OFFSET_HOURS
    delta = vdt - fdt
    return int(round(delta.total_seconds() / 3600.0))


# ------------------------
# Public API
# ------------------------

def clone_schema_stub(ref_path: str | Path, out_path: str | Path, dt: datetime) -> str:
    """
    Clone dims/groups/vars/attrs from ref_path and write an 'empty' stub at out_path for cycle dt.
    - validTime is always written in ISO UTC (YYYY-MM-DDTHH:00:00Z)
    - The hour offset between filename cycle and validTime is preserved from the reference
    Requires: netCDF4, numpy
    """
    import numpy as np
    from netCDF4 import Dataset

    ref_path, out_path = Path(ref_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # We'll detect offset once at the root and reuse for all groups
    detected_offset = 0

    def copy_root_dims(src_root: Dataset, dst_root: Dataset) -> Tuple[dict, set]:
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

        # Check if the dtype is the Python string class or the string 'str'
        if src_var.dtype == str or str(src_var.dtype) == 'str':
            kind = "S"
        else:
            kind = src_var.dtype.kind

        if fv is not None and kind in ("f", "i", "u"):
            dst_var = dst_grp.createVariable(src_var.name, src_var.dtype, src_var.dimensions, fill_value=fv, **kwargs)
        else:
            vtype = "str" if kind in ("S", "U", "O") else src_var.dtype
            dst_var = dst_grp.createVariable(src_var.name, vtype, src_var.dimensions, **kwargs)
        copy_attrs(src_var, dst_var)
        return dst_var

    def write_empty(var, root_dim_sizes: dict, unlimited_names: set):
        import numpy as np
        shape = []
        for dname in var.dimensions:
            if dname in unlimited_names:
                shape.append(1)
            else:
                size = root_dim_sizes.get(dname)
                if size is None:
                    size = 1
                shape.append(size)

        # Check if the dtype is the Python string class or the string 'str'
        if var.dtype == str or str(var.dtype) == 'str':
            kind = "S"
        else:
            kind = var.dtype.kind

        if kind == "f":
            # Write real NaNs for floats so plotting breaks the line at missing points
            var[:] = np.nan
        elif kind in ("i", "u"):
            # Integers (e.g., count) → zero
            var[:] = 0
        else:
            # Strings
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
            if name.lower() == "validtime" and v.ndim == 1 and v.dimensions[0].lower() == "analysiscycle":
                target = _utc(cycle_dt) + timedelta(hours=offset_hours)
                v[0] = _format_valid_iso(target)

    def walk(src_grp, dst_grp, root_dim_sizes: dict, unlimited_names: set, offset_hours: int):
        for _, src_var in src_grp.variables.items():
            dst_var = create_var(src_var, dst_grp)
            write_empty(dst_var, root_dim_sizes, unlimited_names)

        specialize_valid_time(dst_grp, dt, offset_hours)
        copy_attrs(src_grp, dst_grp)

        for gname, src_sub in src_grp.groups.items():
            walk(src_sub, dst_grp.createGroup(gname), root_dim_sizes, unlimited_names, offset_hours)

    from netCDF4 import Dataset  # local import already done
    with Dataset(ref_path, "r") as src, Dataset(out_path, "w", format="NETCDF4") as dst:
        # Detect offset at root using the source file
        ref_vstr = read_ref_validtime_str(src)
        detected_offset = _valid_offset_hours_from_reference(ref_vstr, ref_path.name)

        root_sizes, unlimited = copy_root_dims(src, dst)
        copy_attrs(src, dst)
        walk(src, dst, root_sizes, unlimited, detected_offset)

    return str(out_path)


def guess_domain_size(ob_type: str) -> int:
    """
    Heuristic for Domain dimension (used only for generic stubs).
    You can override with env DEFAULT_DOMAIN_SIZE if desired.
    """
    env = os.getenv("DEFAULT_DOMAIN_SIZE")
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    ob = (ob_type or "").lower()
    if "aod" in ob or "viirs" in ob:
        return 7
    if "snow" in ob or "snocvr" in ob:
        return 10
    return 10


def write_generic_stub(
    out_path: str | Path,
    dt: datetime,
    ob_type: str,
    product_group: str,
    include_gridded_bins: bool = False,
) -> str:
    """
    Minimal EVA-friendly schema (strings + byDomains; optional griddedBins).
    - validTime always ISO (YYYY-MM-DDTHH:00:00Z)
    - Uses DEFAULT_VALIDTIME_OFFSET_HOURS when no reference exists
    """
    from netCDF4 import Dataset
    import numpy as np

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    FILL = np.float32(DEFAULT_FLOAT_FILL)

    # Choose the default offset (constant). If you want per-type, use the commented dict above.
    offset_h = DEFAULT_VALIDTIME_OFFSET_HOURS
    # offset_h = DEFAULT_OFFSET_BY_OBTYPE.get((ob_type or "").lower(), DEFAULT_VALIDTIME_OFFSET_HOURS)

    vtime_dt = _utc(dt) + timedelta(hours=offset_h)
    vtime_str = _format_valid_iso(vtime_dt)

    domain_size = guess_domain_size(ob_type)

    # Default gridded bin sizes (tweak if needed; you can add env overrides later if desired)
    bz, by, bx = 1, 180, 360

    with Dataset(out_path, "w", format="NETCDF4") as nc:
        # Core dims
        nc.createDimension("analysisCycle", None)
        nc.createDimension("Domain", domain_size)

        # Root vars
        vt = nc.createVariable("validTime", str, ("analysisCycle",))
        vt[0] = vtime_str
        sd = nc.createVariable("statisticDomain", str, ("Domain",))
        sd[:] = np.array([f"D{i:02d}" for i in range(1, domain_size + 1)], dtype=object)

        def make_side(parent_grp, side_name: str):
            g = parent_grp.createGroup(side_name).createGroup(product_group)
            mean = g.createVariable("mean", "f4", ("analysisCycle", "Domain"), zlib=True, complevel=1, fill_value=FILL)
            count = g.createVariable("count", "i4", ("analysisCycle", "Domain"), zlib=True, complevel=1)
            rms = g.createVariable("RMS", "f4", ("analysisCycle", "Domain"), zlib=True, complevel=1, fill_value=FILL)
            # Use NaN so line plots show gaps at missing cycles
            mean[:] = np.nan
            count[:] = 0
            rms[:] = np.nan

        # byDomains (always present)
        byDomains = nc.createGroup("byDomains")
        make_side(byDomains, "ombg")
        make_side(byDomains, "oman")

        # Optional gridded bins
        if include_gridded_bins:
            nc.createDimension("binsZDim", bz)
            nc.createDimension("binsYDim", by)
            nc.createDimension("binsXDim", bx)

            def make_grid_side(parent_grp, side_name: str):
                g = parent_grp.createGroup(side_name).createGroup(product_group)
                dims = ("analysisCycle", "binsZDim", "binsYDim", "binsXDim")
                mean = g.createVariable("mean", "f4", dims, zlib=True, complevel=1, fill_value=FILL)
                count = g.createVariable("count", "i4", dims, zlib=True, complevel=1)
                rms = g.createVariable("RMS", "f4", dims, zlib=True, complevel=1, fill_value=FILL)
                mean[:] = np.nan
                count[:] = 0
                rms[:] = np.nan

            gridded = nc.createGroup("griddedBins")
            make_grid_side(gridded, "ombg")
            make_grid_side(gridded, "oman")

    return str(out_path)


__all__ = [
    "DEFAULT_FLOAT_FILL",
    "clone_schema_stub",
    "write_generic_stub",
    "guess_domain_size",
]
