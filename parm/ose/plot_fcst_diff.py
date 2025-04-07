import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapGridded, MapContour

opserrpath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/diff/gdas.20250310/12/atmos/gdas.t12z.f120.ops.diff.nc'
opspath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/ops/gfs.20250310/12/atmos/gfs.t12z.pgrb2.0p25.f120.nc'
anlpath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/ops/gfs.20250315/12/atmos/gfs.t12z.pgrb2.0p25.anl.nc'
oseerrpath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/diff/gdas.20250310/12/atmos/gdas.t12z.f120.prsondes.diff.nc'
osepath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/prsonde/gfs.20250310/12/atmos/gfs.t12z.pgrb2.0p25.f120.nc'

opserr = nc.Dataset(opserrpath)
anl = nc.Dataset(anlpath)
ops = nc.Dataset(opspath)
oseerr = nc.Dataset(oseerrpath)
ose = nc.Dataset(osepath)

lat = opserr.variables['latitude'][:]
lon = opserr.variables['longitude'][:]
lons, lats = np.meshgrid(lon, lat)

# 500 hPa Heights
opserr_500hgt = opserr.variables['HGT_500mb'][:]
oseerr_500hgt = oseerr.variables['HGT_500mb'][:]
ops_500hgt = ops.variables['HGT_500mb'][:]
ose_500hgt = ose.variables['HGT_500mb'][:]
anl_500hgt = anl.variables['HGT_500mb'][:]

# absolute value of differences
diff_500hgt = np.abs(opserr_500hgt) - np.abs(oseerr_500hgt)

# plot
gridded = MapGridded(lats, lons, diff_500hgt[0,...])
gridded.cmap = 'bwr'
gridded.vmin = -30
gridded.vmax = 30
contour = MapContour(lats, lons, anl_500hgt[0,...])
contour.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
plot1 = CreatePlot()
plot1.plot_layers = [gridded,contour]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='Forecast height error relative to analysis',
                    fontsize=12, extend='neither')
plot1.add_title(label='Difference in forecast relative to analysis\n500 hPa heights   abs(GFSanl - GFSf120) - abs(GFSanl - EXPf120)\nInit: 2025031012 Valid: 2025031512',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/hgt500_fcst_diff_2025031012_2025031512.png')

# plot all 3 contours on one plot
contouranl = MapContour(lats, lons, anl_500hgt[0,...])
contouranl.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
contourops = MapContour(lats, lons, ops_500hgt[0,...])
contourops.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
contourops.colors = 'blue'
contourose = MapContour(lats, lons, ose_500hgt[0,...])
contourose.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
contourose.colors = 'red'
plot1 = CreatePlot()
plot1.plot_layers = [contouranl, contourops, contourose]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_title(label='500 hPa height contours\nGFS-analysis: black -- GFS-fh120: blue -- EXP-fh120: red\nInit: 2025031012 Valid: 2025031512',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/hgt500_contours_2025031012_2025031512.png')
