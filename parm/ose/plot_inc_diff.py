import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapGridded

incdiffpath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/ose/diff.atminc.nc'
anldiffpath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/ose/diff.atmanl.nc'
anlpath = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/ose/exp/gdas.t00z.atmanl.nc'

incdiff = nc.Dataset(incdiffpath)
anldiff = nc.Dataset(anldiffpath)
anl = nc.Dataset(anlpath)

# plot increment diffs




# plot anl diffs
# get lat and lons
lats = anl.variables['lat'][:]
lons = anl.variables['lon'][:]

temp = anldiff.variables['tmp'][:]
ps = anldiff.variables['pressfc'][:]
u = anldiff.variables['ugrd'][:]

print(temp.shape)
print(temp[0,95,...])
print(np.nanmax(temp[0,95,...]))

gridded = MapGridded(lats, lons, temp[0,95,...])
gridded.cmap = 'bwr'
gridded.vmin = -1
gridded.vmax = 1
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
plot1.add_title(label='Difference in analysis fields\n~800hPa      2025030800',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/anl_800_tmp_diff.png')

gridded = MapGridded(lats, lons, u[0,95,...])
gridded.cmap = 'bwr'
gridded.vmin = -3
gridded.vmax = 3
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='U wind',
                    fontsize=12, extend='neither')
plot1.add_title(label='Difference in analysis fields\n~800hPa      2025030800',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/anl_800_u_diff.png')

gridded = MapGridded(lats, lons, u[0,95,...])
gridded.cmap = 'bwr'
gridded.vmin = -5
gridded.vmax = 5
plot1 = CreatePlot()
plot1.plot_layers = [gridded]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_colorbar(label='Ps (Pa)',
                    fontsize=12, extend='neither')
plot1.add_title(label='Difference in analysis fields\nsurface     2025030800',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
fig.save_figure('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/anl_ps_diff.png')