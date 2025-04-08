import numpy as np
import matplotlib.pyplot as plt
#import netCDF4 as nc
import grib2io
import os
import datetime as dt
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapGridded, MapContour

ops_root = '/lfs/h2/emc/global/noscrub/cory.r.martin/ops_gfsv16.3'
para_root = '/lfs/h2/emc/ptmp/russ.treadon/prsonde'
fh = 120

inits = [dt.datetime(2025,3,10,12),
         dt.datetime(2025,3,11,0),
         dt.datetime(2025,3,11,12),
         dt.datetime(2025,3,12,0),
         dt.datetime(2025,3,12,12),
         dt.datetime(2025,3,13,0),
         ]
valid = [dt.datetime(2025,3,15,12),
         dt.datetime(2025,3,16,0),
         dt.datetime(2025,3,16,12),
         dt.datetime(2025,3,17,0),
         dt.datetime(2025,3,17,12),
         dt.datetime(2025,3,18,0),
         ]

for i in range(len(inits)):
    anlpath = os.path.join(ops_root, f"gdas.{valid[i].strftime('%Y%m%d')}",
                           valid[i].strftime('%H'), "atmos", f"gdas.t{valid[i].strftime('%H')}z.pgrb2.0p25.anl")
    opspath = os.path.join(ops_root, f"gfs.{inits[i].strftime('%Y%m%d')}",
                           inits[i].strftime('%H'), "atmos", f"gfs.t{inits[i].strftime('%H')}z.pgrb2.0p25.f120")
    parapath = os.path.join(para_root, f"gfs.{inits[i].strftime('%Y%m%d')}",
                            inits[i].strftime('%H'), "atmos", f"gfs.t{inits[i].strftime('%H')}z.pgrb2.0p25.f120")
    # open grib files
    ops = grib2io.open(opspath)
    para = grib2io.open(parapath)
    anl = grib2io.open(anlpath)

    # get 500mb hgts
    hgt500_ops = ops.select(shortName='HGT', level='500 mb')[0]
    hgt500_para = para.select(shortName='HGT', level='500 mb')[0]
    hgt500_anl = anl.select(shortName='HGT', level='500 mb')[0]

    # get grid
    lats, lons = hgt500_ops.grid()

    # get data
    hgt500_ops_data = hgt500_ops.data
    hgt500_para_data = hgt500_para.data
    hgt500_anl_data = hgt500_anl.data

    # derive fields
    ops_abs_err = np.abs(hgt500_anl_data - hgt500_ops_data)
    para_abs_err = np.abs(hgt500_anl_data - hgt500_para_data)
    errchg = para_abs_err - ops_abs_err

    # ops error
    contour = MapContour(lats, lons, hgt500_anl_data)
    contour.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
    gridded = MapGridded(lats, lons, ops_abs_err)
    gridded.cmap = 'YlOrRd'
    gridded.vmin = 0
    gridded.vmax = 100
    plot1 = CreatePlot()
    plot1.plot_layers = [gridded, contour]
    plot1.projection = 'plcarr'
    plot1.domain = 'conus'
    plot1.add_map_features(['coastline', 'states'])
    plot1.add_colorbar(label='Absolute Error (m)', fontsize=8, extend='neither')
    plot1.add_title(label='Shading: GFS Forecast Error   Contour: GDAS Analysis', loc='center', fontsize=10)

    # para error
    contour = MapContour(lats, lons, hgt500_anl_data)
    contour.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
    gridded = MapGridded(lats, lons, para_abs_err)
    gridded.cmap = 'YlOrRd'
    gridded.vmin = 0
    gridded.vmax = 100
    plot2 = CreatePlot()
    plot2.plot_layers = [gridded, contour]
    plot2.projection = 'plcarr'
    plot2.domain = 'conus'
    plot2.add_map_features(['coastline', 'states'])
    plot2.add_colorbar(label='Absolute Error (m)', fontsize=8, extend='neither')
    plot2.add_title(label='Shading: Experiment Forecast Error   Contour: GDAS Analysis', loc='center', fontsize=10)

    # err change
    contour = MapContour(lats, lons, hgt500_anl_data)
    contour.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
    gridded = MapGridded(lats, lons, errchg)
    gridded.cmap = 'bwr'
    gridded.vmin = -50
    gridded.vmax = 50
    plot3 = CreatePlot()
    plot3.plot_layers = [gridded, contour]
    plot3.projection = 'plcarr'
    plot3.domain = 'conus'
    plot3.add_map_features(['coastline', 'states'])
    plot3.add_colorbar(label='Absolute Error Change (m)', fontsize=8, extend='neither')
    plot3.add_title(label='Shading: Forecast Error Change   Contour: GDAS Analysis', loc='center', fontsize=10)

    # spaghetti panel
    contour1 = MapContour(lats, lons, hgt500_anl_data)
    contour1.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
    contour2 = MapContour(lats, lons, hgt500_ops_data)
    contour2.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
    contour2.colors = 'blue'
    contour3 = MapContour(lats, lons, hgt500_para_data)
    contour3.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
    contour3.colors = 'red'
    plot4 = CreatePlot()
    plot4.plot_layers = [contour1, contour2, contour3]
    plot4.projection = 'plcarr'
    plot4.domain = 'conus'
    plot4.add_map_features(['coastline', 'states'])
    plot4.add_title(label="black: GDAS analysis    blue: GFS f120   red: EXP f120", loc='center', fontsize=10)

    # create figure
    fig = CreateFigure(nrows=2, ncols=2, figsize=(12,8))
    fig.plot_list = [plot1, plot2, plot3, plot4]
    fig.create_figure()
    fig.add_suptitle(f"500 hPa Heights\nInit: {inits[i].strftime('%Y%m%d%H')}    Valid: {valid[i].strftime('%Y%m%d%H')}    Forecast Hour: {fh}")
    fig.plot_logo(loc='lower right', subplot_orientation='last', zoom=0.2, alpha=0.9)
    fig.save_figure(f"4panel_init_{inits[i].strftime('%Y%m%d%H')}_valid_{valid[i].strftime('%Y%m%d%H')}.png")


#g = grib2io.open(expf120path)
#print(g)
#hgt500 = g.select(shortName='HGT', level='500 mb')[0]
#hgt500data = hgt500.data
#lats, lons = hgt500.grid()
#
## plot all 3 contours on one plot
#contour = MapContour(lats, lons, hgt500data)
#contour.levels = [5220,5280,5340,5400,5460,5520,5580,5640,5700,5760,5820]
#plot1 = CreatePlot()
#plot1.plot_layers = [contour]
#plot1.projection = 'plcarr'
#plot1.domain = 'conus'
#plot1.add_map_features(['coastline', 'states'])
#plot1.add_xlabel(xlabel='longitude')
#plot1.add_ylabel(ylabel='latitude')
#plot1.add_title(label='500 hPa height contours\nInit: 2025031100 Valid: 2025031600',
#                loc='left', fontsize=12)
#plot1.add_grid()
#
#fig = CreateFigure()
#fig.plot_list = [plot1]
#fig.create_figure()
#fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)
#fig.save_figure('hgt500_contours_2025031100_2025031600.png')
