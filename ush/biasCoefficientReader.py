from netCDF4 import Dataset
import numpy as np
import netCDF4 as nc
import argparse
from datetime import datetime


def read_ncfile(file):
    """
    Read and extract bias coefficient data.

    Parameters:
        file (str): path to input netCDF4 file
    Return:
        d (dict): dictionary of data 
    """
    d = {}

    with Dataset(file, mode='r') as f:
        for var in ['predictors', 'nchannels', 'bias_coefficients']:
            data = f.variables[var][:]
            d[var] = data

    return d


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
    epoch_time = np.array([int(dt_object.timestamp())])

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

    epoch_var = nc_file.createVariable('epoch_time', np.int64, ('validTime',))

    for key, value in outdata.items():
        if isinstance(value, np.ma.MaskedArray):
            data = np.array([value.data])
        else:
            data = np.array([value])

        var = nc_file.createVariable(key, np.float32, ('validTime', 'Channel',))
        var[:] = data

    # Close the netCDF file
    nc_file.close()

    return


def main(input_file, cycle, outfile):
    """
    Extract bias coefficient information from a netCDF4 file and output it
    to a new netCDF file with time information.

    Parameters:
        input_file (str): input bias coefficient .nc file
        cycle (str): cycle in YYYYMMDDHH
        outfile (str):  path and filename for new .nc file
    Return:
        None
    """

    data_dict = read_ncfile(input_file)

    outdata = {pred: data_dict['bias_coefficients'][i] for i, pred in enumerate(data_dict['predictors'])}

    # Datetime to epoch time
    epoch_time = datetime2epoch(cycle)

    # Grab number of channels
    nchannels = len(data_dict['nchannels'])

    # Write out ncfile
    write_ncfile(outfile, outdata, epoch_time, nchannels)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument('-f', '--inputfile', type=str, help='Input bias coefficient file', required=True)
    parser.add_argument('-c', '--cycle', type=str, help='Cycle YYYYMMDDHH', required=True)
    parser.add_argument('-o', '--outfile', type=str, help='Path and filename of output nc file', required=True)
    args = parser.parse_args()

    main(args.inputfile, args.cycle, args.outfile)
