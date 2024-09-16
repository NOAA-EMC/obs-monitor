
import argparse
import yaml
import os
from re import sub
from datetime import datetime
from eva.utilities.logger import Logger
from wxflow import add_to_datetime, to_timedelta, to_datetime

data_dir_struct = ["obs-mon", "glb-wkflw", "gfs-ops", "leg-mon"]
ozn_instruments = ['gome', 'omi', 'ompslp', 'ompsnp', 'ompstc8']


class OM_data:

    def __init__(self, data_src, config, plot_yaml, logger):

        self.pdate = datetime.strftime(config.get('PDATE'), '%Y%m%d%H')
        self.data_src = data_src
#        self.config = config
#        self.data_dest = data_dest
        self.logger = logger
        self.data_dir_type = ""
        self.plot_dict = {}
        self.ctl_file = None
        self.data_files = []
        self.dir_struct= ""

        self.read_yaml(plot_yaml)
        self.load_data_files()
        self.set_data_type(config.get('SAT'), config.get('SENSOR'))
        self.set_dir_struct()

        self.dump()
        
# --------------------------------------------------------------------------------------------
    def dump(self):
        self.logger.info(f'dump OM_data:')
        self.logger.info(f'==== =======')
        self.logger.info(f'    data_type: {self.data_type}')
        self.logger.info(f'        pdate: {self.pdate}')
        self.logger.info(f'     data_src: {self.data_src}')
#       self.logger.info(f'       config: {self.config}')
#       self.logger.info(f'    plot_dict: {self.plot_dict}')
        self.logger.info(f'     ctl_file: {self.ctl_file}')
        self.logger.info(f'   data_files: {self.data_files}')

#       self.logger(f'data_dest: {self.data_dest}')
#       self.logger(f'data_dir_type: {self.data_dir_type}')
#       for df in self.data_files:
#           self.logger.info(f'     {df}')

# --------------------------------------------------------------------------------------------
    def set_data_type(self, sat, sensor):

        if sensor in ozn_instruments:
            type = 'ozn'
        elif sat is not None:
            type = 'rad' 
        else:
            type = None
        self.data_type = type

# --------------------------------------------------------------------------------------------
    def read_yaml(self, yaml_file):
        """
        Read yaml file into plot_dict

        Parameters:
            yaml_file (file): yaml file with dict info
            logger (Logger): Logger object for logging messages.

        Return:
            dictionary from yaml_file
        """

        pd = None
        try:
            with open(yaml_file, 'r') as yaml_file_opened:
                pd = yaml.safe_load(yaml_file_opened)

        except Exception as e:
            self.logger.info('Warning: unable to load yaml file into rtn_dict ' +
                             f'errors when attempting to load: {yaml_file}, error: {e}')
        self.plot_dict = pd

# --------------------------------------------------------------------------------------------
    def load_data_files(self):

        """

        Parameters:
        Return:
        """
        self.logger.info(f'--> load_data_files')

        #  Note it's possible to have more than 1 dataset so this will need to iterate
        ds = self.plot_dict.get('datasets')
        ds = ds[0]

        self.ctl_file = os.path.basename(ds['control_file'][0])
        self.data_files = [os.path.basename(f) for f in ds['filenames']]
        self.logger.info(f'<-- load_data_files')

# --------------------------------------------------------------------------------------------
    def set_dir_struct(self):
        ###
        ###
 
        self.logger.info(f'--> set_dir_struct')
        self.dir_struct = 'obs-mon'

        if os.path.exists(os.path.join(self.data_src, self.data_type + '_data')):
            self.logger.info(f'JACKPOT!')

#(os.path.join(os.getcwd(), 'new_folder', 'file.txt')):

        self.logger.info(f'<-- set_dir_struct')


def locate_data(sat, sensor, data_path, cycle_times, logger):
    """
    Locate required data files, testing for each of the 4 possible
    data storage schemes.

    Parameters:
        sat (string): satellite name
        sensor (string): sensor (instrument) name
        data_path (str): input data path from config file
        cycle_times (list): list of required cycle times
        logger (Logger): Logger object for logging messages.

    Return:
        list of required data files (full path)
    """

    logger.info(f'<-- locate_data')
    df = []

    for cyc in cycle_times:
        file = get_data_file(sat, sensor, data_path, cyc, logger, model='gfs', component='ges')
        logger.info(f'file: {file}')

    logger.info(f'<-- locate_data')
    return df

# --------------------------------------------------------------------------------------------
def get_dir_type(data_location, data_type, pdate, ctl_file, logger):
    """
    Determine the type of data file structure pointed to by data_location.

    Parameters:
        data_location (str): path to data files.
        data_type (str): type of data [con|min|ozn|rad]
        pdate (datetime): plot date.
        ctl_file (str): control file name
        logger (Logger): Logger object for logging messages.

    Return:
        dir type as enumerated in data_dir_struct list or None
    """

    logger.info(f'--> get_dir_type')
    logger.info(f'data_location: {data_location}')

#   data_dir_struct = ["obs-mon", "glb-wkflw", "gfs-ops", "leg-mon"]

    for dir in data_dir_struct:
        logger.info(f'testing dir: {dir}')

    logger.info(f'<-- get_dir_type')
    return None

# --------------------------------------------------------------------------------------------
def load_data(data_location, config, plot_yaml, logger):
    """
    Determine necessary data and control files for plotting and untar/copy/link into
    local work space directory.

    Parameters:
        data_location (str): path to data files
        config
        plot_yaml (file): yaml file with plot information
        logger (Logger): Logger object for logging messages.

    Return:
        None
    """

    logger.info(f'--> load_data')

    sat = config.get('SAT')
    sensor = config.get('SENSOR')
    pdate = datetime.strftime(config.get('PDATE'), '%Y%m%d%H')
    pdy = pdate[:-2]
    hh = pdate[-2:]
    logger.info(f' pdate, pdy, hh: {pdate} {pdy} {hh}')

    # for the moment assume only OZN data
    data_type = 'ozn'
 
    # load plot_yaml and return the control and list of data files
    ctl_file, data_files = getfiles(data_location, plot_yaml, pdate, logger)

    # determine type of data directory structure
    dir_type = get_dir_type(data_location, data_type, pdate, ctl_file, logger)
 
    # iterate over data_files and copy/link to cwd
 

    # this should tell us what kind of data we're after
#   plot_template = config.get('PLOT_TEMPLATE')
#   logger.info(f'plot_template: {plot_template}')

#   if sat is not None:
#       logger.info(f'SAT IS NOT NONE')
   
#   if is_ozn_data(sensor):
#       logger.info(f'OZN DATA')
#   else:
#       logger.info(f"NOPE ISN'T OZN DATA")

#   filtered_values = [value for key, value in config.items() if key.startswith('PDATEm')] 
#   cycle_times = [datetime.strftime(value, '%Y%m%d%H') for value in filtered_values]
#   logger.info(f'cycle_times: {cycle_times}')

#   data_files = locate_data(sat, sensor, cycle_times, data_path, logger)

    logger.info(f'<-- load_data')

# --------------------------------------------------------------------------------------------


def setupdata(data_location, config, plot_yaml, logger):
    """
    Read in config and plot_yaml file and set up required data files locally.

    Parameters:
        data_location (str): path to data files
        plot_yaml (file): yaml file with plot information
        logger (Logger): Logger object for logging messages.

    Return:
        None
    """

    logger.info(f'--> setupdata')
    logger.info(f' data_location: {data_location}')
    logger.info(f' plot_yaml: {plot_yaml}')
    logger.info(f' config: {config}')

    # Load data into local directory
    load_data(data_location, config, plot_yaml, logger)
    
    logger.info(f'<-- setupdata')

#   try:
#       mon_sources = args.input
#       with open(mon_sources, 'r') as mon_sources_opened:
#           mon_dict = yaml.safe_load(mon_sources_opened)
#   except Exception as e:
#       logger.abort('setUpData is expecting a valid model plot yaml file, but encountered ' +
#                    f'errors when attempting to load: {mon_sources}, error: {e}')

#   try:
#       cycles = get_cycles(args.pdate, logger)
#       logger.info(f'cycles: {cycles}')
        
#   except Exception as e:
#       logger.abort('setUpData is expecting a valid pdate but encountered ' +
#                    f'errors when attempting to load: {mon_sources}, error: {e}')
