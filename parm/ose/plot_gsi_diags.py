from pyGSI.diags import Conventional
import numpy as np
import matplotlib.pyplot as plt
import netCDF4 as nc
from emcpy.plots import CreatePlot, CreateFigure
from emcpy.plots.map_tools import Domain, MapProjection
from emcpy.plots.map_plots import MapScatter

diagnosticFile = '/scratch2/NCEPDEV/stmp1/Cory.R.Martin/apr2025/raobs/diag_conv_t_ges.2025040100.nc4'
diag = Conventional(diagnosticFile)

DiagData = diag.get_data()

DiagData_plains = DiagData[DiagData['latitude'] > 37]
DiagData_plains = DiagData_plains[DiagData_plains['latitude'] < 46]
DiagData_plains = DiagData_plains[DiagData_plains['longitude'] > 256]
DiagData_plains = DiagData_plains[DiagData_plains['longitude'] < 267]

OmF_plains = DiagData_plains['omf_adjusted']
print(OmF_plains[0])

OmF_plains_sfc = OmF_plains[OmF_plains['Pressure'] > 850]
OmF_plains_midtrop = OmF_plains[OmF_plains['Pressure'] < 850]
OmF_plains_midtrop = OmF_plains_midtrop[OmF_plains_midtrop['Pressure'] > 400]
OmF_plains_uprtrop = OmF_plains[OmF_plains['Pressure'] < 400]
OmF_plains_uprtrop = OmF_plains_uprtrop[OmF_plains_uprtrop['Pressure'] > 200]
print(OmF_plains_sfc)
print(OmF_plains_midtrop)
print(OmF_plains_uprtrop)