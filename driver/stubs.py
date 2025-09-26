# stubs.py
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import os
from typing import Tuple

# Keep this consistent with your real files
DEFAULT_FLOAT_FILL = -3.368795e38


# ------------------------
# Helpers
# ------------------------

def _dt_str(dt: datetime) -> str:
    """UTC timestamp as YYYYMMDDHH string."""
    return dt.astimezone(timezone.utc).strftime("%Y%m%d%H")


# ------------------------
# Public API
# ------------------------

def clone_schema_stub(ref_path: str | Path, out_path: str | Path, dt: datetime) -> str:
    """
    Clone dims/groups/vars/attrs from ref_path and write an 'empty' stub at out_path for cycle dt.
    - Unlimited dims are created unlimited; we write a single record along them.
    - Numeric vars are filled with _FillValue (if present), otherwise 0 for ints / DEFAULT_FLOAT_FILL for floats.
    - String vars are filled with 'NA', except 'validTime' gets YYYYMMDDHH at index 0.
    Requires: netCDF4, numpy
    """
    import numpy as np
    from netCDF4 import Dataset

    ref_path, out_path = Path(ref_path), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vtime_str = _dt_str(dt)

    # We only create dimensions at the root (like most files); subgroups will reference them by name.
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
            # _FillValue must be set at var creation time; skip copying as an attribute
            if att == "_FillValue":
                continue
            try:
                dst_obj.setncattr(att, src_obj.getncattr(att))
            except Exception:
                # Be tolerant of odd attr types
                pass

    def create_var(src_var, dst_grp):
        """Create a destination variable mirroring dtype/dims, with light compression for arrays."""
        kwargs = {}
        if src_var.ndim > 0:
            kwargs = dict(zlib=True, complevel=1)

        # Detect fill value if numeric
        try:
            fv = src_var.getncattr("_FillValue")
        except Exception:
            fv = None

        # Determine dtype for strings (vlen) vs numeric
        kind = src_var.dtype.kind
        if fv is not None and kind in ("f", "i", "u"):
            dst_var = dst_grp.createVariable(
                src_var.name, src_var.dtype, src_var.dimensions, fill_value=fv, **kwargs
            )
        else:
            vtype = "str" if kind in ("S", "U", "O") else src_var.dtype
            dst_var = dst_grp.createVariable(src_var.name, vtype, src_var.dimensions, **kwargs)

        copy_attrs(src_var, dst_var)
        return dst_var

    def write_empty(var, root_dim_sizes: dict, unlimited_names: set):
        """Fill the variable with appropriate 'empty' values, writing 1 record along unlimited dims."""
        import numpy as np

        # Build the target shape (1 along unlimited, fixed size otherwise)
        shape = []
        for dname in var.dimensions:
            if dname in unlimited_names:
                shape.append(1)
            else:
                # root_dim_sizes[dname] must exist for standard files
                size = root_dim_sizes.get(dname)
                if size is None:  # None only for unlimited dims, already handled
                    size = 1
                shape.append(size)

        kind = var.dtype.kind
        if kind in ("f", "i", "u"):
            try:
                fill = var.getncattr("_FillValue")
            except Exception:
                fill = 0 if kind in ("i", "u") else DEFAULT_FLOAT_FILL
            # Note: assign a scalar; netCDF4 will broadcast
            var[:] = (0 if kind in ("i", "u") else fill)
        else:
            # Strings: fill with "NA"
            arr = np.empty(shape, dtype=object)
            arr.fill("NA")
            var[:] = arr

    def specialize_valid_time(grp, vtime: str):
        """Set validTime[0] = vtime where applicable."""
        for name, v in grp.variables.items():
            if name.lower() == "validtime" and v.ndim == 1 and v.dimensions[0].lower() == "analysiscycle":
                v[0] = vtime

    def walk(src_grp, dst_grp, root_dim_sizes: dict, unlimited_names: set):
        # Variables
        for _, src_var in src_grp.variables.items():
            dst_var = create_var(src_var, dst_grp)
            write_empty(dst_var, root_dim_sizes, unlimited_names)

        # validTime specialization (after empty write)
        specialize_valid_time(dst_grp, vtime_str)

        # Group attributes
        copy_attrs(src_grp, dst_grp)

        # Recurse into subgroups
        for gname, src_sub in src_grp.groups.items():
            dst_sub = dst_grp.createGroup(gname)
            walk(src_sub, dst_sub, root_dim_sizes, unlimited_names)

    with Dataset(ref_path, "r") as src, Dataset(out_path, "w", format="NETCDF4") as dst:
        # 1) Root dims (once)
        root_sizes, unlimited = copy_root_dims(src, dst)
        # 2) Root attrs
        copy_attrs(src, dst)
        # 3) Root vars + groups
        walk(src, dst, root_sizes, unlimited)

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
    Minimal EVA-friendly schema for time series:
      - root strings: validTime(analysisCycle), statisticDomain(Domain)
      - byDomains/ombg/<product_group> : mean,count,RMS (analysisCycle,Domain)
      - byDomains/oman/<product_group> : mean,count,RMS (analysisCycle,Domain)
      - [optional] griddedBins/{ombg,oman}/<product_group> : mean,count,RMS (analysisCycle,binsZDim,binsYDim,binsXDim)
    Bin sizes default to (1, 180, 360); override with env BINS_Z / BINS_Y / BINS_X if needed.
    Requires: netCDF4, numpy
    """
    from netCDF4 import Dataset
    import numpy as np

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    FILL = np.float32(DEFAULT_FLOAT_FILL)
    vtime = _dt_str(dt)
    domain_size = guess_domain_size(ob_type)

    # Optional env overrides for gridded bin sizes
    bz = int(os.getenv("BINS_Z", "1"))
    by = int(os.getenv("BINS_Y", "180"))
    bx = int(os.getenv("BINS_X", "360"))

    with Dataset(out_path, "w", format="NETCDF4") as nc:
        # Core dims
        nc.createDimension("analysisCycle", None)
        nc.createDimension("Domain", domain_size)

        # Root vars
        vt = nc.createVariable("validTime", str, ("analysisCycle",))
        vt[0] = vtime
        sd = nc.createVariable("statisticDomain", str, ("Domain",))
        sd[:] = np.array([f"D{i:02d}" for i in range(1, domain_size + 1)], dtype=object)

        def make_side(parent_grp, side_name: str):
            g = parent_grp.createGroup(side_name).createGroup(product_group)
            mean  = g.createVariable("mean",  "f4", ("analysisCycle", "Domain"), zlib=True, complevel=1, fill_value=FILL)
            count = g.createVariable("count", "i4", ("analysisCycle", "Domain"), zlib=True, complevel=1)
            rms   = g.createVariable("RMS",   "f4", ("analysisCycle", "Domain"), zlib=True, complevel=1, fill_value=FILL)
            mean[:] = FILL
            count[:] = 0
            rms[:] = FILL

        # byDomains group (always)
        byDomains = nc.createGroup("byDomains")
        make_side(byDomains, "ombg")
        make_side(byDomains, "oman")

        # Optional griddedBins groups
        if include_gridded_bins:
            nc.createDimension("binsZDim", bz)
            nc.createDimension("binsYDim", by)
            nc.createDimension("binsXDim", bx)

            def make_grid_side(parent_grp, side_name: str):
                g = parent_grp.createGroup(side_name).createGroup(product_group)
                dims = ("analysisCycle", "binsZDim", "binsYDim", "binsXDim")
                mean  = g.createVariable("mean",  "f4", dims, zlib=True, complevel=1, fill_value=FILL)
                count = g.createVariable("count", "i4", dims, zlib=True, complevel=1)
                rms   = g.createVariable("RMS",   "f4", dims, zlib=True, complevel=1, fill_value=FILL)
                mean[:] = FILL
                count[:] = 0
                rms[:] = FILL

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
