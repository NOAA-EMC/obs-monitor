import argparse
import yaml
from netCDF4 import Dataset
import numpy as np
import netCDF4 as nc
from datetime import datetime


def read_ncfile(file, group_list):
    """
    Read and extract data from ncfile based on inputted groups.
    """
    d = {}

    with Dataset(file, mode='r') as f:
        for g in group_list:
            md = f.groups[g]

            d[g] = {}

            for var in md.variables:
                data = md.variables[var][:]
                d[g][var] = data

    return d


def calculate_omf(data_dict, input1, variable, biascorrection=True, input2=None):
    """
    Calculate observation minus forecast for data that is bias corrected and not bias corrected.
    """
    try:
        omf = data_dict['ObsValue'][variable] - data_dict[input1][variable]

        if biascorrection:
            return omf
        else:
            return omf - data_dict[input2][variable]

    except KeyError as error:
        print(f"Calculation failed. Missing input group variable: {error}")


def calculate_penalty(data_dict, omf, input1, variable):
    """
    Calculates penalty by observation minus forecast by effective error.
    """
    try:
        penalty = omf / data_dict[input1][variable]

        return penalty

    except KeyError as error:
        print(f"Calculation failed. Missing input group variable: {error}")


def datetime2epoch(cycle):
    """
    Convert a datetime in str to epoch time.
    """
    # Convert string to datetime object
    dt_object = datetime.strptime(cycle, '%Y%m%d%H')

    # Convert datetime object to Unix epoch time (seconds since January 1, 1970)
    epoch_time = np.array([int(dt_object.timestamp())])

    return epoch_time


def write_ncfile(outfile, outdata, epoch_time):
    """
    Write an ncfile from dictionary.
    """
    # Create a new netCDF file
    nc_file = nc.Dataset(outfile, 'w', format='NETCDF4')

    valid_time_dim = nc_file.createDimension('validTime', 1)
    channel_dim = nc_file.createDimension('Channel', 22)

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
    """
    # Grab config info ##

    data_dict = read_ncfile(input_file, group_names)

    omgbc0 = calculate_omf(data_dict, input1='hofx0', variable=group_variable)
    omgbc1 = calculate_omf(data_dict, input1='hofx1', variable=group_variable)
    omgnbc0 = calculate_omf(data_dict, input1='hofx0', variable=group_variable,
                            biascorrection=False, input2='ObsBias0')
    omgnbc1 = calculate_omf(data_dict, input1='hofx1', variable=group_variable,
                            biascorrection=False, input2='ObsBias1')
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

    # Create outdata dictionary
    outdata = {i: {} for i in outvars}

    # Loop through data to clean data and calculate counts, mean, and std
    for i, data in enumerate(data_list):
        # Get list of out dict keys
        key = list(outdata.keys())[i]

        extreme_indices = np.where((data > 1e6) | (data < -1e6))

        # Replace bad data with nans
        data[extreme_indices] = np.nan

        # Calculate counts, mean, standard deviation not including nans
        counts = np.count_nonzero(~np.isnan(data), axis=0)
        mean = np.nanmean(data, axis=0)
        std = np.nanstd(data, axis=0)

        outdata[key]['count'] = counts
        outdata[key]['mean'] = mean
        outdata[key]['std'] = std

    # Get epoch time
    epoch_time = datetime2epoch(cycle)

    # Write out ncfile
    write_ncfile(outfile, outdata, epoch_time)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', type=str, help='Input YAML file', required=True)
    parser.add_argument('-c', '--cycle', type=str, help='Plot time YYYYMMDDHH', required=True)
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
            if satellite == 'ssmis':
                group_names.append('cos', 'sin')
            group_variable = group.get('variable')

            main(filename, cycle, satellite, channels,
                 outvars, outfile, group_names, group_variable)
