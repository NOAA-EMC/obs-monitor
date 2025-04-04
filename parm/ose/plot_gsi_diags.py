from pyGSI.diags import Conventional
import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapScatter

diagnosticFile = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/diag_conv_t_ges.2025030100.nc4'
diag = Conventional(diagnosticFile)

DiagData = diag.get_data()

# DiagData_plains = DiagData[DiagData['latitude'] > 37]
# DiagData_plains = DiagData_plains[DiagData_plains['latitude'] < 46]
# DiagData_plains = DiagData_plains[DiagData_plains['longitude'] > 256]
# DiagData_plains = DiagData_plains[DiagData_plains['longitude'] < 267]
DiagData_plains = DiagData[DiagData['latitude'] > 20]
DiagData_plains = DiagData_plains[DiagData_plains['latitude'] < 50]
DiagData_plains = DiagData_plains[DiagData_plains['longitude'] > 230]
DiagData_plains = DiagData_plains[DiagData_plains['longitude'] < 300]

DiagData_plains_sfc = DiagData_plains.query("(Pressure > 850.0) and (Analysis_Use_Flag == 1.0)")
DiagData_plains_midtrop = DiagData_plains.query("(Pressure > 400.0) and (Pressure <= 850.0) and (Analysis_Use_Flag == 1.0)")
DiagData_plains_uprtrop = DiagData_plains.query("(Pressure > 150.0) and (Pressure <= 400.0) and (Analysis_Use_Flag == 1.0)")

OmF_plains_sfc = DiagData_plains_sfc['omf_adjusted']
OmF_plains_midtrop = DiagData_plains_midtrop['omf_adjusted']
OmF_plains_uprtrop = DiagData_plains_uprtrop['omf_adjusted']

print(OmF_plains_sfc.min(),OmF_plains_sfc.max(),OmF_plains_sfc.mean())
print(OmF_plains_midtrop.min(),OmF_plains_midtrop.max(),OmF_plains_midtrop.mean())
print(OmF_plains_uprtrop.min(),OmF_plains_uprtrop.max(),OmF_plains_uprtrop.mean())
print(OmF_plains_uprtrop.values)

# near surface plot
scatter = MapScatter(DiagData_plains_sfc['latitude'].values, DiagData_plains_sfc['longitude'].values, OmF_plains_sfc.values)
scatter.cmap = 'bwr'
scatter.vmin = -3
scatter.vmax = 3
# Create plot object and add features
plot1 = CreatePlot()
plot1.plot_layers = [scatter]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_title(label='Conventional T OmF - Assimilated Obs > 850 hPa - 2025030100', loc='center',
                fontsize=10)
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)

plt.savefig('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/omf_nearsurface_conv_t_2025030100.png')

# mid trop plot
scatter = MapScatter(DiagData_plains_midtrop['latitude'].values, DiagData_plains_midtrop['longitude'].values, OmF_plains_midtrop.values)
scatter.cmap = 'bwr'
scatter.vmin = -3
scatter.vmax = 3
# Create plot object and add features
plot1 = CreatePlot()
plot1.plot_layers = [scatter]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_title(label='Conventional T OmF - Assimilated Obs 400-850 hPa - 2025030100', loc='center',
                fontsize=10)
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
#fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)

plt.savefig('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/omf_midtrop_conv_t_2025030100.png')

# upr trop plot
scatter = MapScatter(DiagData_plains_uprtrop['latitude'].values, DiagData_plains_uprtrop['longitude'].values, OmF_plains_uprtrop.values)
scatter.cmap = 'bwr'
scatter.vmin = -3
scatter.vmax = 3
# Create plot object and add features
plot1 = CreatePlot()
plot1.plot_layers = [scatter]
plot1.projection = 'plcarr'
plot1.domain = 'conus'
plot1.add_map_features(['coastline', 'states'])
plot1.add_xlabel(xlabel='longitude')
plot1.add_ylabel(ylabel='latitude')
plot1.add_title(label='Conventional T OmF - Assimilated Obs 150-400 hPa - 2025030100', loc='center',
                fontsize=10)
plot1.add_colorbar(label='temperature',
                    fontsize=12, extend='neither')
fig = CreateFigure()
fig.plot_list = [plot1]
fig.create_figure()
fig.plot_logo(loc='lower right', subplot_orientation='first', zoom=0.5, alpha=0.9)

plt.savefig('/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/figs/omf_uprtrop_conv_t_2025030100.png')
