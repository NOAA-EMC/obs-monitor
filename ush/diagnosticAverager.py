import argparse
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
        groups (list): list of strings that contains group names from input .nc file
        variable (str): variable within input .nc file groups
        channels (list): channels where data should be grabbed
        logger : logging variable that tracks progress of source code
    Return:
        return_dict (dict): dictionary of data
    """
    return_dict = {}

    try:
        with Dataset(file, mode='r') as f:
            # Grab index of input channels
            chan_numbers = f.groups['MetaData'].variables['sensorChannelNumber'][:][0]
            chan_idx = np.where(np.in1d(chan_numbers, channels))[0]

            for g in groups:
                return_dict[g] = {}
                gd = f.groups[g]

                data = gd.variables[variable][:]
                return_dict[g][variable] = data[:, chan_idx]

    except Exception as e:
        logger.abort("Extraction of data failed. Ensure group exists " +
                     f"in input .ncfile. Error: {e}")

    return return_dict


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
    epoch_time = int(dt_object.timestamp())

    return epoch_time


def calculate_omf(filename, inputdict, logger):
    """
    Calculate observation minus forecast for data that is bias corrected and not bias corrected.

    Parameters:
        filename (str): input path and filename to netCDF file to be read
        inputdict (dict): dictionary of input variables needed to extract data
        logger : logging variable that tracks progress of source code
    Return:
        return_dict (dict): dictionary of observation minus forecast values
    """

    loops = inputdict.get('loops')
    variable = inputdict.get('variable')
    channels = inputdict.get('channels')
    bias_corr = inputdict.get('bias correction')
    outgroups = inputdict.get('groups out')

    if len(loops) != len(outgroups):
        logger.abort("In the input .yaml file, `loops` must be the same " +
                     "len as `groups out`. Exiting ...")

    return_dict = {}

    for i, loop in enumerate(loops):
        groups = [f'hofx{loop}', 'ObsValue', f'ObsBias{loop}']

        # Grab data from .nc file
        data_dict = read_ncfile(filename, groups, variable, channels, logger)

        return_dict[outgroups[i]] = {}

        omf = data_dict['ObsValue'][variable] - data_dict[f'hofx{loop}'][variable]

        if bias_corr:
            return_dict[outgroups[i]]['data'] = omf
        else:
            return_dict[outgroups[i]]['data'] = omf - bias_dict[f'obsBias{loop}'][variable]

        return_dict[outgroups[i]]['qc var'] = f'EffectiveQC{loop}'

    return return_dict


def calculate_penalty(filename, inputdict, logger):
    """
    Calculates penalty by dividing observation minus forecast by effective error.

    Parameters:
        filename (str): input path and filename to netCDF file to be read
        inputdict (dict): dictionary of input variables needed to extract data
        logger : logging variable that tracks progress of source code
    Return:
        return_dict (dict): dictionary of penalty values
    """

    loops = inputdict.get('loops')
    variable = inputdict.get('variable')
    channels = inputdict.get('channels')
    outgroups = inputdict.get('groups out')

    if len(loops) != len(outgroups):
        logger.abort("In the input .yaml file, `loops` must be the same " +
                     "len as `groups out`. Exiting ...")

    return_dict = {}

    omf_dict = calculate_omf(filename, inputdict, logger)

    for i, loop in enumerate(loops):

        efferr_dict = read_ncfile(filename, [f'EffectiveError{loop}'], variable, channels, logger)

        return_dict[outgroups[i]] = {}

        for key in omf_dict.keys():

            return_dict[outgroups[i]]['data'] = omf_dict[key]['data'] / efferr_dict[f'EffectiveError{loop}'][variable]
            return_dict[outgroups[i]]['qc var'] = f'EffectiveQC{loop}'

    return return_dict


def grab_data(filename, inputdict, logger):
    """
    Grabs data from input .nc file

    Paramaters:
        filename (str): input path and filename to netCDF file to be read
        inputdict (dict): dictionary of input variables needed to extract data
        logger : logging variable that tracks progress of source code
    Return:
        return_dict (dict): dictionary of data values
    """

    groups = inputdict.get('groups')
    variable = inputdict.get('variable')
    channels = inputdict.get('channels')
    qcvar = inputdict.get('qc var')
    outgroups = inputdict.get('groups out')

    if len(groups) != len(outgroups):
        logger.abort("In the input .yaml file, `groups` must be the same " +
                     "len as `groups out`. Exiting ...")

    return_dict = {}

    for i, group in enumerate(groups):
        outgroup_key = outgroups[i]
        return_dict[outgroup_key] = {}

        data_dict = read_ncfile(filename, [group], variable, channels, logger)

        return_dict[outgroup_key]['data'] = data_dict[group][variable]
        return_dict[outgroup_key]['qc var'] = qcvar

    return return_dict


def main(filename, cycle, satellite, channels, variable, config_data, outfile, logger):
    """
    Read in JEDI diagnostic file, calculate counts, averages, and standard
    deviation, and output results to a new netCDF file with time information.

    Parameters:
        filename (str): input path and filename to netCDF file to be read
        cycle (str): forecast run cycle in YYYYMMDDHH
        satellite (str): name of satellite from input data
        channels (list): channels where data should be grabbed
        variable (str): variable used within input .nc file to extract data
        qcvar (str): quality control variable to use to clean data
        config_data (dict): dictionary of related information pulled from input yaml file
        outfile (str): path and filename for new .nc file
        logger : logging variable that tracks progress of source code
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
        # Extract function name
        function = inputdict.get('function')

        # Call function from factory
        data = factory[function](filename, inputdict, logger)

        outdata.update(data)

    # Loop through data to clean data and calculate counts, mean, and std
    for key in outdata.keys():

        data = outdata[key]['data']
        qcvar = outdata[key]['qc var']
        outdata[key].pop('qc var', None)

        # TEMP FIX: User submitted QC variable in input yaml
        effective_qc = read_ncfile(filename, [qcvar], variable, channels, logger)
        qc_indices = np.where(effective_qc[qcvar][variable] != 0)

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
    epoch_time = np.array([datetime2epoch(cycle)])

    # Grab number of channels
    nchannels = len(channels)

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
        channels = data.get('channels')
        variable = data.get('variable')
        config_data = data.get('variables to process')
        outfile = data.get('outfile')

    main(filename, cycle, satellite, channels, variable, config_data, outfile, logger)
