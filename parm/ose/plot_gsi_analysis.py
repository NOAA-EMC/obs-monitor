import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapGridded

# open netCDF files for writing
anl1 = nc.Dataset('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/gdas.t00z.atmanl.nc')
anl2 = nc.Dataset('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/gdas.t06z.atmanl.nc')

# get lat and lons
lats = anl1.variables['lat'][:]
lons = anl1.variables['lon'][:]

# try for just temp first
temp1 = anl1.variables['tmp'][:]
temp2 = anl2.variables['tmp'][:]

# difference
temp_diff = temp1-temp2

# plot on a map
gridded = MapGridded(lats, lons, temp_diff[0, -1,...])
gridded.cmap = 'bwr'
gridded.vmin = -20
gridded.vmax = 20
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
plot1.add_title(label='Difference in analysis fields',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/surface_temp_anl_diff.png')

# plot analysis field
gridded = MapGridded(lats, lons, temp1[0, -1,...])
gridded.cmap = 'rainbow'
gridded.vmin = 260
gridded.vmax = 310
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
plot1.add_title(label='analysis field',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/surface_temp_anl.png')