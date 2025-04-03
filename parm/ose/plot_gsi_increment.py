import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapGridded

# open netCDF files for writing
inc1 = nc.Dataset('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/gdas.t00z.atminc.nc')
inc2 = nc.Dataset('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/gdas.t06z.atminc.nc')

# get lat and lons
lat = inc1.variables['lat'][:]
lon = inc1.variables['lon'][:]
lons, lats = np.meshgrid(lon, lat)

# try for just temp first
temp1 = inc1.variables['T_inc'][:]
temp2 = inc2.variables['T_inc'][:]

# difference
temp_diff = temp1-temp2

# plot on a map
gridded = MapGridded(lats, lons, temp_diff[-1,...])
gridded.cmap = 'bwr'
gridded.vmin = -1
gridded.vmax = 1
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
plot1.add_title(label='Difference in increment fields',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/surface_temp_inc_diff.png')

# plot increment field
gridded = MapGridded(lats, lons, temp1[-1,...])
gridded.cmap = 'bwr'
gridded.vmin = -10
gridded.vmax = 10
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
plot1.add_title(label='increment field',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/surface_temp_inc.png')