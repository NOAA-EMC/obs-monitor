import numpy as np
import matplotlib.pyplot as plt
#import netCDF4 as nc
import grib2io
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapGridded, MapContour

expf120path = '/lfs/h2/emc/ptmp/russ.treadon/prsonde/gfs.20250311/00/atmos/gfs.t00z.pgrb2.0p25.f120'

g = grib2io.open(expf120path)
print(g)
hgt500 = g.select(shortName='HGT', level='500 mb')[0]
hgt500data = hgt500.data
lats, lons = hgt500.grid()

# plot all 3 contours on one plot
contour = MapContour(lats, lons, hgt500data)
contour.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
plot1 = CreatePlot()
plot1.plot_layers = [contour]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_title(label='500 hPa height contours\nInit: 2025031100 Valid: 2025031600',
                loc='left', fontsize=12)
plot1.add_grid()

fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
fig.save_figure('hgt500_contours_2025031100_2025031600.png')
