import argparse
import yaml
from netCDF4 import Dataset
import numpy as np
import netCDF4 as nc
from datetime import datetime


def read_ncfile(file, group_list):
    """
    Read and extract data from ncfile based on inputted groups.

    Parameters:
        file (str): path to input netCDF4 file
        group_list (list): list of strings representing the groups needed in
                           nc file
    Return:
        d (dict): dictionary of data
    """
    d = {}

    with Dataset(file, mode='r') as f:
        for g in group_list:
            gd = f.groups[g]

            d[g] = {}

            for var in gd.variables:
                data = gd.variables[var][:]
                d[g][var] = data

    return d


def calculate_omf(data_dict, hofx, variable, biascorrection=True, obsbias=None):
    """
    Calculate observation minus forecast for data that is bias corrected and not bias corrected.

    Parameters:
        data_dict (dict): dictionary of data from input nc file
        hofx (str): the hofx variable to be used (i.e. hofx0, hofx1)
        variable (str): group variable specified in input yaml file
        biascorrection (bool): if using bias corrected data, set to True. If using no bias
                               corrected data, set to False
        obsbias (str): the obs bias variable to be used (i.e. ObsBias0, ObsBias1). Only needed
                       if biascorrection=False
    Return:
        omf (array): the observation minus forecast result
    """
    try:
        omf = data_dict['ObsValue'][variable] - data_dict[hofx][variable]

        if biascorrection:
            return omf
        else:
            return omf - data_dict[obsbias][variable]

    except KeyError as error:
        print(f"Calculation failed. Missing input group variable: {error}")


def calculate_penalty(data_dict, omf, obsbias, variable):
    """
    Calculates penalty by observation minus forecast by effective error.

    Parameters:
        data_dict (dict):  dictionary of data from input nc file
        omf (array): observation minus forecast array
        obsbias (str): the obs bias variable to be used (i.e. ObsBias0, ObsBias1)
        variable (str): group variable specified in input yaml file
    Return:
        penalty (array): observation minus forecast divided by observation bias array
    """
    try:
        penalty = omf / data_dict[obsbias][variable]

        return penalty

    except KeyError as error:
        print(f"Calculation failed. Missing input group variable: {error}")


def datetime2epoch(cycle):
    """
    Convert a datetime in str to epoch time.

    Parameters:
        cycle (str): date of cycle in YYYYMMDDHH
    Return:
        epoch_time (int): value of time in seconds since Jan. 1, 1970
    """
    # Convert string to datetime object
    dt_object = datetime.strptime(cycle, '%Y%m%d%H')

    # Convert datetime object to Unix epoch time (seconds since January 1, 1970)
    epoch_time = [int(dt_object.timestamp())]

    return epoch_time


def write_ncfile(outfile, outdata, epoch_time, nchannels):
    """
    Write an ncfile from dictionary.

    Parameters:
        outfile (str): path and file name of where the data is to be written to specified
                       in input yaml
        outdata (dict): data collected from input netCDF file with calculated statistics
        epoch_time (str): cycle time as seconds from Jan. 1, 1970
        nchannels (int): total number of channels
    Return:
        None
    """
    # Create a new netCDF file
    nc_file = nc.Dataset(outfile, 'w', format='NETCDF4')

    valid_time_dim = nc_file.createDimension('validTime', 1)
    channel_dim = nc_file.createDimension('Channel', nchannels)

    # Loop through the keys in the dictionary
    for key, value in outdata.items():
        # Create a group with the key as its name
        group = nc_file.createGroup(key)

        epoch_var = group.createVariable('epoch_time', np.int64, ('validTime',))
        epoch_var[:] = epoch_time

        # Loop through the nested keys and add variables
        for nested_key, nested_value in value.items():
            if isinstance(nested_value, np.ma.MaskedArray):
                data = np.array([nested_value.data])
            else:
                data = np.array([nested_value])

            var = group.createVariable(nested_key, np.float32, ('validTime', 'Channel',))
            var[:] = data

    # Close the netCDF file
    nc_file.close()

    return


def main(input_file, cycle, satellite, channels, outvars, outfile, group_names, group_variable):
    """
    Read in config file contaiting bias corrected data, calculate counts, averages, and standard
    deviation, and output results to a new netCDF file with time information.

    Parameters:
        input_file (str): input path and filename to netCDF file to be read
        cycle (str): cycle in YYYYMMDDHH
        satellite (str): name of satellite from input data
        channels (str): channels where data should be grabbed
        outvars (list): list of strings of the desired variables to be saved to new .nc file
        outfile (file): path and filename for new .nc file
        group_names (list): list of strings that contains group names from input .nc file
        group_variable (str): variable within input .nc file groups
    Return:
        None
    """
    # Grab config info
    data_dict = read_ncfile(input_file, group_names)

    # Can this block be better??
    omgbc0 = calculate_omf(data_dict, hofx='hofx0', variable=group_variable)
    omgbc1 = calculate_omf(data_dict, hofx='hofx1', variable=group_variable)
    omgnbc0 = calculate_omf(data_dict, hofx='hofx0', variable=group_variable,
                            biascorrection=False, obsbias='ObsBias0')
    omgnbc1 = calculate_omf(data_dict, hofx='hofx1', variable=group_variable,
                            biascorrection=False, obsbias='ObsBias1')
    penalty0 = calculate_penalty(data_dict, omgbc0, input1='ObsBias0', variable=group_variable)
    penalty1 = calculate_penalty(data_dict, omgbc1, input1='ObsBias1', variable=group_variable)
    obsbias0 = data_dict['ObsBias0'][group_variable]
    obsbias1 = data_dict['ObsBias1'][group_variable]
    lapserate1 = data_dict['lapse_ratePredictor'][group_variable]
    lapserate2 = data_dict['lapse_rate_order_2Predictor'][group_variable]
    constant = data_dict['constantPredictor'][group_variable]
    emissivity = data_dict['emissivityPredictor'][group_variable]
    scanangle = data_dict['scan_anglePredictor'][group_variable]
    scanangle2 = data_dict['scan_angle_order_2Predictor'][group_variable]
    scanangle3 = data_dict['scan_angle_order_3Predictor'][group_variable]
    scanangle4 = data_dict['scan_angle_order_4Predictor'][group_variable]

    data_list = [omgbc0, omgbc1, omgnbc0, omgnbc1, penalty0, penalty1,
                 obsbias0, obsbias1, lapserate1, lapserate2, constant,
                 emissivity, scanangle, scanangle2, scanangle3, scanangle4]
 
    #########################################################################

    # Create outdata dictionary
    outdata = {i: {} for i in outvars}

    # Loop through data to clean data and calculate counts, mean, and std
    for i, data in enumerate(data_list):
        # Get list of out dict keys
        key = list(outdata.keys())[i]

        # Find and replace bad values with nans
        extreme_indices = np.where((data > 1e6) | (data < -1e6))
        data[extreme_indices] = np.nan

        # Calculate counts, mean, standard deviation not including nans
        counts = np.count_nonzero(~np.isnan(data), axis=0)
        mean = np.nanmean(data, axis=0)
        std = np.nanstd(data, axis=0)

        outdata[key]['count'] = counts
        outdata[key]['mean'] = mean
        outdata[key]['std'] = std

    # Get epoch time
    epoch_time = np.array(datetime2epoch(cycle))

    # Grab number of channels
    nchannels = len(data_dict['nchannels'])

    # Write out ncfile
    write_ncfile(outfile, outdata, epoch_time, nchannels)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', type=str, help='Input YAML file', required=True)
    parser.add_argument('-c', '--cycle', type=str, help='Cycle time YYYYMMDDHH', required=True)
    args = parser.parse_args()

    cycle = args.cycle
    infile = args.input

    try:
        with open(infile, 'r') as infile_opened:
            config_dict = yaml.safe_load(infile_opened)
    except Exception as e:
        print('dead')

    for data in config_dict.get('datasets'):
        satellite = data.get('satellite')
        filename = data.get('filename')
        channels = data.get('channels')
        outvars = data.get('outvars')
        outfile = data.get('outfile')

        for group in data.get('groups'):
            group_names = group.get('names')
            # This will need to be tested in future
            if satellite == 'ssmis':
                group_names.append('cos', 'sin')
            group_variable = group.get('variable')

            main(filename, cycle, satellite, channels,
                 outvars, outfile, group_names, group_variable)
