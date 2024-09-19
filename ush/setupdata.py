import argparse
import yaml
import os
import shutil
import gzip
import glob

from re import sub
from datetime import datetime
from eva.utilities.logger import Logger
from wxflow import add_to_datetime, to_timedelta, to_datetime

#data_dir_struct = ["obs-mon", "glb-wkflw", "gfs-ops", "leg-mon"]
#ozn_instruments = ['gome', 'omi', 'ompslp', 'ompsnp', 'ompstc8']


class OM_data:

    def __init__(self, data_src, config, plot_yaml, logger):

        logger.info(f'cwd: {os.getcwd()}')

        self.pdate = datetime.strftime(config.get('PDATE'), '%Y%m%d%H')
        self.data_src = data_src
        self.config = config
#       self.data_dest = ""
        self.logger = logger
        self.data_dir_type = ""
        self.plot_dict = {}
        self.ctl_file = None
        self.data_files = []
        self.dir_struct= ""

        self.read_yaml(plot_yaml)
        self.load_data_files()
        self.set_data_types(os.path.basename(config.get('PLOT_TEMPLATE')))
        self.set_dir_struct()

        self.dump()
        self.copy_data(os.getcwd())        
# --------------------------------------------------------------------------------------------
    def dump(self):
        self.logger.info('')
        self.logger.info(f'dump OM_data:')
        self.logger.info(f'==== =======')
        self.logger.info(f'    data_type: {self.data_type}')
        self.logger.info(f' data_subtype: {self.data_subtype}')
        self.logger.info(f'        pdate: {self.pdate}')
        self.logger.info(f'     data_src: {self.data_src}')
        self.logger.info(f'       config: {self.config}')
#       self.logger.info(f'    plot_dict: {self.plot_dict}')
        self.logger.info(f'     ctl_file: {self.ctl_file}')
        self.logger.info(f'   data_files: {self.data_files}')

#       self.logger(f'data_dest: {self.data_dest}')
#       self.logger(f'data_dir_type: {self.data_dir_type}')
#       for df in self.data_files:
#           self.logger.info(f'     {df}')
        self.logger.info('')

# --------------------------------------------------------------------------------------------
    def set_data_types(self, template):

        self.data_type = template[:3].lower()
        self.data_subtype = template[3:].lower()

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

        path = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'products', 'atmos', 'oznmon', 'horiz', self.ctl_file)
        self.logger.info(f'path: {path}')
 
        if os.path.exists(os.path.join(self.data_src, self.data_type + '_data')):
            self.dir_struct = 'obs-mon'
        elif os.path.exists(os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'products', 'atmos', 'oznmon', 'horiz', self.ctl_file)):
            self.dir_struct = 'glb-wkflw'

#(os.path.join(os.getcwd(), 'new_folder', 'file.txt')):

# --------------------------------------------------------------------------------------------
    def copy_data(self, target_dir ):
        ###
        ###

        self.logger.info(f'--> copy_data')

        match self.dir_struct:
            case 'obs-mon':
                src = os.path.join(self.data_src, self.data_type + '_data/' + self.data_subtype, self.ctl_file)

                # this picks up a potentially gzipped ctl file
                for f in glob.glob(src + '*'):
                    shutil.copy(f, target_dir)
                
                for file in self.data_files:
                    src = os.path.join(self.data_src, self.data_type + '_data/' + self.data_subtype, file)
                    for f in glob.glob(src + '*'):
                        shutil.copy(f, target_dir)
                        
            case 'glb-wkflw':
                src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'products', 'atmos', 'oznmon', 'horiz', self.ctl_file)

                # This picks up a potentially gzipped ctl file.
                # This could be a method().
                for f in glob.glob(src + '*'):
                    shutil.copy(f, target_dir)

                for file in self.data_files:
                    fname = os.path.basename(file)
                    date = fname.split(".")[2]
                    pdy = date[:-2]
                    hh = date[-2:]
                    fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', 'oznmon', 'horiz', fname)

                    # this picks up a potentially gzipped ctl file
                    for f in glob.glob(fsrc + '*'):
                        shutil.copy(f, target_dir)

#           Need to handle these two cases
#           case 'gfs-ops':
#           case 'leg-mon':

            case _:
                self.logger.info(f'no match on dir_struct {self.dir_struct}')

        for f in glob.glob(target_dir + '/*.gz'):
            os.system(f'gunzip {f}')

        self.logger.info(f'<-- copy_data')


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
