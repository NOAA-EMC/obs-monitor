import yaml
from netCDF4 import Dataset
import numpy as np
import netCDF4 as nc
from datetime import datetime
from eva.utilities.logger import Logger


def read_ncfile(file, groups, variable, channels, logger):
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

    try:
        with Dataset(file, mode='r') as f:
            # Grab index of input channels
            chan_numbers = f.groups['MetaData'].variables['sensorChannelNumber'][:][0]
            chan_idx = np.where(np.in1d(chan_numbers, channels))[0]
            
            for g in groups:
                d[g] = {}
                gd = f.groups[g]

                data = gd.variables[variable][:]
                d[g][variable] = data[:, chan_idx]

    except Exception as e:
        logger.abort("Extraction of data failed. Ensure group exists " +
                     f"in input .ncfile. Error: {e}")

    return d


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


def calculate_omf(filename, groups, variable, channels, outgroups, bias_corr, bias_groups, logger):
    """
    Calculate observation minus forecast for data that is bias corrected and not bias corrected.

    Parameters:
        filename (str): input path and filename to netCDF file to be read
        groups (list): list of strings that contains group names from input .nc file
        variable (str): variable within input .nc file groups
        channels (array): channels where data should be grabbed
        outgroups (list): list of strings that contains the group names for the output .nc file
        bias_corr (bool): boolean value to determine if bias correction was used or not
        bias_groups (list): list of observation bias values to be used from input .nc file
    Return:
        return_dict (dict): dictionary of observation minus forecast values
    """
    # Add 'ObsValue' to groups to calculate omf
    groups.append('ObsValue')

    # Grab data from .nc file
    data_dict = read_ncfile(filename, groups, variable, channels, logger)

    # Calculate omf
    return_dict = {}

    for i, output in enumerate(outgroups):
        return_dict[output] = {}

        hofx = groups[i]
        omf = data_dict['ObsValue'][variable] - data_dict[hofx][variable]

        if bias_corr:
            return_dict[output]['data'] = omf
        else:
            bias_dict = read_ncfile(filename, bias_groups, variable, channels, logger)
            obsbias = bias_groups[i]

            return_dict[output]['data'] = omf - bias_dict[obsbias][variable]

    return return_dict


def calculate_penalty(filename, groups, variable, channels, outgroups, logger):
    """
    Calculates penalty by observation minus forecast by effective error.

    Parameters:
        filename (str): input path and filename to netCDF file to be read
        groups (list): list of strings that contains group names from input .nc file
        variable (str): variable within input .nc file groups
        channels (array): channels where data should be grabbed
        outgroups (list): list of strings that contains the group names for the output .nc file
    Return:
        return_dict (dict): dictionary of penalty values
    """
    return_dict = {}

    omf_dict = calculate_omf(filename, groups, variable, channels, outgroups, bias_corr=True,
                             bias_groups=None, logger)

    # logic check to see how many effective errors you need?
    efferr = ['EffectiveError0', 'EffectiveError1']

    efferr_dict = read_ncfile(filename, efferr, variable, channels, logger)

    for i, output in enumerate(outgroups):
        return_dict[output] = {}

        for k, key in enumerate(omf_dict.keys()):

            return_dict[output]['data'] = omf_dict[key]['data'] / efferr_dict[efferr[k]][variable]

    return return_dict


def grab_data(filename, groups, variable, channels, outgroups, logger):
    """
    Grabs data from input .nc file

    Paramaters:
        filename (str): input path and filename to netCDF file to be read
        groups (list): list of strings that contains group names from input .nc file
        variable (str): variable within input .nc file groups
        channels (array): channels where data should be grabbed
        outgroups (list): list of strings that contains the group names for the output .nc file
    Return:
        return_dict (dict): dictionary of data values
    """
    return_dict = {}

    for i, group in enumerate(groups):
        outgroup_key = outgroups[i]
        return_dict[outgroup_key] = {}

        data_dict = read_ncfile(filename, [group], variable, channels, logger)

        return_dict[outgroup_key]['data'] = data_dict[group][variable]

    return return_dict


def main(filename, cycle, satellite, config_data, outfile):
    """
    Read in JEDI diagnostic config file, calculate counts, averages, and standard
    deviation, and output results to a new netCDF file with time information.

    Parameters:
        filename (str): input path and filename to netCDF file to be read
        cycle (str): forecast run cycle in YYYYMMDDHH
        satellite (str): name of satellite from input data
        config_data (dict): dictionary of related information pulled from input yaml file
        outfile (str): path and filename for new .nc file
    Return:
        None
    """

    factory = {
        'calculate_omf': calculate_omf,
        'calculate_penalty': calculate_penalty,
        'grab_data': grab_data
    }

    outdata = {}

    for inputdict in config_data:
        function = inputdict.get('function')
        groups = inputdict.get('groups')
        variable = inputdict.get('variable')
        channels = inputdict.get('channels')
        out_groups = inputdict.get('groups out')

        # I think I am going to need a logic check
        # i.e. len(groups) == len(groups out)
        # if calling penalty, omf needs to exist? Have same inputs
        # as `calculate_omf` and then just call omf, and then subtract
        # effective error?

        if 'bias corrected' in inputdict.keys():
            bc_dict = inputdict.get('bias corrected')[0]

            bias_corr = bc_dict.get('bias correction used')
            bias_groups = bc_dict.get('bias groups')

            data = factory[function](filename, groups, variable, channels, out_groups, bias_corr,
                                     bias_groups, logger)

        else:
            data = factory[function](filename, groups, variable, channels, out_groups, logger)

        outdata.update(data)

    # Loop through data to clean data and calculate counts, mean, and std
    for key in outdata.keys():

        data = outdata[key]['data']

        # Find and replace bad values with nans
        # This is tricky: How can I do this for the correct EffectiveQC value?
        # What is the correct QC value?
        effective_qc = read_ncfile(filename, ['EffectiveQC0'], variable, channels, logger)
        qc_indices = np.where(effective_qc['EffectiveQC0']['brightnessTemperature'] != 0)

        data[qc_indices] = np.nan

        # Calculate counts, mean, standard deviation not including nans
        counts = np.count_nonzero(~np.isnan(data), axis=0)
        mean = np.nanmean(data, axis=0)
        std = np.nanstd(data, axis=0)

        outdata[key]['count'] = counts
        outdata[key]['mean'] = mean
        outdata[key]['std'] = std

        # Remove data from outdata dictionary
        outdata[key].pop('data', None)

    # Get epoch time
    epoch_time = np.array(datetime2epoch(cycle))

    # Grab number of channels
    nchannels = len(data_dict['nchannels'])

    # Write out ncfile
    write_ncfile(outfile, outdata, epoch_time, nchannels)


if __name__ == "__main__":

    logger = Logger('biasCorrectionReader')
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
        logger.abort(f"Input yaml file unable to load. See error: {e}")

    for data in config_dict.get('datasets'):
        satellite = data.get('satellite')
        filename = data.get('filename')
        config_data = data.get('variables to process')
        outfile = data.get('outfile')

    main(filename, cycle, satellite, config_data, outfile, logger)
