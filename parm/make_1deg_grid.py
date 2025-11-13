import xarray as xr
import numpy as np

ny, nx = 180, 360                      # binsYDim, binsXDim
lats = np.linspace(-89.5,  89.5, ny)   # centers
lons = np.linspace(  0.5, 359.5, nx)   # 0–360 centers (use -179.5..179.5 if preferred)

Lon2D, Lat2D = np.meshgrid(lons, lats)  # shapes (ny, nx)

ds = xr.Dataset(
    {
        "latitude":  (("binsYDim", "binsXDim"), Lat2D),
        "longitude": (("binsYDim", "binsXDim"), Lon2D),
    },
    coords={"binsYDim": np.arange(ny), "binsXDim": np.arange(nx)},
)
ds.to_netcdf("./grid_def_1deg_centers.nc")
