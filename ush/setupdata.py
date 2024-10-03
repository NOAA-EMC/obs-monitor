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


class OM_data:

    def __init__(self, data_src, config, plot_yaml, logger):

        self.pdate = datetime.strftime(config.get('PDATE'), '%Y%m%d%H')
        self.data_src = data_src
        self.logger = logger
        self.data_dir_type = ""
        self.plot_dict = {}
        self.ctl_file = []
        self.data_files = []
        self.dir_struct = ""
        self.data_type = ""
        self.data_subtype = ""
        self.use_subtype = False

        self.read_yaml(plot_yaml)
        self.load_data_files()
        self.set_data_types(os.path.basename(config.get('PLOT_TEMPLATE')))
        self.set_dir_struct()

        self.dump()
        self.copy_data(os.getcwd())        
# --------------------------------------------------------------------------------------------
    def dump(self):
        """
        Dump all current values in object of class OM_data via logger.info.

        Paremeters:
            None
        Return:
            None
        """

        self.logger.info('')
        self.logger.info(f'dump OM_data:')
        self.logger.info(f'==== =======')
        self.logger.info(f'    data_type: {self.data_type}')
        self.logger.info(f' data_subtype: {self.data_subtype}')
        self.logger.info(f'        pdate: {self.pdate}')
        self.logger.info(f'     data_src: {self.data_src}')
        self.logger.info(f'     ctl_file: {self.ctl_file}')
        self.logger.info(f'   data_files: {self.data_files}')
        self.logger.info(f'   dir_struct: {self.dir_struct}')

# maybe dump plot_dict as separate method
#       self.logger.info(f'    plot_dict: {self.plot_dict}')

        self.logger.info('end dump OM_data')
        self.logger.info('=== ==== =======')
        self.logger.info('')


# --------------------------------------------------------------------------------------------
    def set_data_types(self, template):
    
        self.data_type = template[:3].lower()
        stype = template[3:].lower() 

        # summary will have to point to time, min type doesn't have a subtype
        if stype == 'summary' and self.data_type != 'min':
            stype = 'time'
        self.data_subtype = stype

        if self.data_type == 'ozn':
            self.use_subtype = True

        if self.data_type == 'con':
            self.use_subtype = True
            if stype in ['time', 'vert']:
                self.data_subtype = 'time_vert'
            elif stype in ['hist', 'horz']:
                self.data_subtype = 'horz_hist'

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
        Load control and data file names from plot_dict into OM_data class object.
   
        Parameters:
            None
        Return:
            None
        """

        ds = self.plot_dict.get('datasets')

        for d in ds:
            if 'control_file' in d.keys():
                self.ctl_file.append(os.path.basename(d['control_file'][0]))
            self.data_files.append([os.path.basename(f) for f in d['filenames']])

# --------------------------------------------------------------------------------------------
    def set_dir_struct(self):
        """
        Determine which data directory structure is in use. Supported structures are:
            obs-mon:   used for testing, data is simply in 'ozn_data', 'rad_data', etc.  
            glb-wkflw: global workflow structure
            gfs-ops:   operational gfs structure
            leg-mon:   legacy DA monitor structure

        Parameters:
            None
        Return:
            None
        """
        mon = self.data_type + 'mon'
        om_test = os.path.join(self.data_src, self.data_type + '_data')
        gw_test = ""
        go_test = "" 
        lm_test = ""

        match mon:
            case 'oznmon':
                gw_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                       'products', 'atmos', mon, self.data_subtype)
                go_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                       'atmos', mon, self.data_subtype)
                lm_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                       mon, self.data_subtype)

            case 'radmon':
                gw_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:],
                              'products', 'atmos', mon, mon + '_' + self.data_subtype + '.tar.gz')
                go_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:],
                              'atmos', mon, mon + '_' + self.data_subtype + '.tar.gz')
                lm_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                              mon, mon + '_' + self.data_subtype + '.tar.gz')

            case 'minmon':
                gw_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'products', 'atmos', mon)
                go_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'atmos', mon)
                lm_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], mon) 

            # conmon is only in obs-mon and leg-mon structures
            case 'conmon':
                lm_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                       mon, self.data_subtype, self.ctl_file[0])
                
        if os.path.exists(om_test):
            self.dir_struct = 'obs-mon'
        elif os.path.exists(gw_test):
            self.dir_struct = 'glb-wkflw'
        elif os.path.exists(go_test):
            self.dir_struct = 'gfs-ops'
        elif os.path.exists(lm_test):
            self.dir_struct = 'leg-mon'


# --------------------------------------------------------------------------------------------
    def get_rad_datafile(self, cycle, file, dest_dir):
        """
        Legacy radmon data is unique in that it is stored in tar files (to reduce file
        count).  There are 4 files for each cycle: radmon_angle.tar.gz, radon_bcoef.tar.gz,
        radmon_bcor.tar.gz, and radmon_time.tar.gz.  The input file name will be extracted 
        (if present) from the specified tar file.

        Note that data in obs-mon structure (used only for development) is simply a 
        directory containing uncompressed files (not stored in a tar file).

        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name 
            dest_dir (path):  full directory path to where data file is to be extracted. 
        Return:
            None

        """

        pdy = cycle[:-2]
        hh = cycle[-2:]

        match self.dir_struct:
            case 'obs-mon':
                tarfile = ""
                f = os.path.join(self.data_src, 'rad_data', file) 
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)

            case 'glb-wkflw':
                tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', 'radmon', 'radmon_' + self.data_subtype + '.tar.gz')
            case 'gfs-ops':
                tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', 'radmon', 'radmon_' + self.data_subtype + '.tar.gz')
            case 'leg-mon':
                tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'radmon', 'radmon_' + self.data_subtype + '.tar.gz')

        if os.path.isfile(tarfile):
            os.system('tar -xf ' + tarfile + ' -C ' + dest_dir + ' --wildcards ' + file + '*')

# --------------------------------------------------------------------------------------------
    def get_ozn_datafile(self, cycle, file, dest_dir):
        """
        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name 
            dest_dir (path):  full directory path to where data file is to be extracted. 
        Return:
            None

        """

        pdy = cycle[:-2]
        hh = cycle[-2:]

        match self.dir_struct:
            case 'obs-mon':
                f = os.path.join(self.data_src, 'ozn_data', self.data_subtype, file) 
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)
#           case 'glb-wkflw':
#               tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', 'radmon', 'radmon_' + self.data_subtype + '.tar.gz')
            case 'gfs-ops':
                ff = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', 'oznmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
            case 'leg-mon':
                ff = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'oznmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)

# --------------------------------------------------------------------------------------------
    def get_min_datafile(self, cycle, file, dest_dir):
        """
        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name 
            dest_dir (path):  full directory path to where data file is to be extracted. 
        Return:
            None

        """

        pdy = cycle[:-2]
        hh = cycle[-2:]
        self.logger.info(f'--> get_min_datafile, cycle: {cycle}, file: {file}, des_dir: {dest_dir}')
        self.logger.info(f' self.dir_struct: {self.dir_struct}')

        match self.dir_struct:
            case 'obs-mon':
                f = os.path.join(self.data_src, 'min_data', file) 
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)
#           case 'glb-wkflw':
#               self.logger.info(f'case glb-wkflw not yet supported') 
#               tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', 'radmon', 'radmon_' + self.data_subtype + '.tar.gz')
            case 'gfs-ops':
                ff = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', 'minmon', file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
            case 'leg-mon':
                ff = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'minmon', file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
                 
# --------------------------------------------------------------------------------------------
    def get_con_datafile(self, cycle, file, dest_dir):
        """
        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name 
            dest_dir (path):  full directory path to where data file is to be extracted. 
        Return:
            None

        """

        pdy = cycle[:-2]
        hh = cycle[-2:]
      
        match self.dir_struct:
            case 'obs-mon':
                f = os.path.join(self.data_src, 'con_data', self.data_subtype, file) 
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)
            case 'glb-wkflw':
                self.logger.info(f'case glb-wkflw not yet supported') 
            case 'gfs-ops':
                self.logger.info(f'case gfs-ops not yet supported') 
            case 'leg-mon':
                ff = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'conmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
                 

# --------------------------------------------------------------------------------------------
    def copy_data(self, dest_dir ):
        """
        Copy required data and control files to requested directory.

        Parameters:
            dest_dir (path): directory to which data is to be copied
        Return:
            None
        """

        self.logger.info(f'dest_dir: {dest_dir}')
        self.logger.info(f'self.use_subtype: {self.use_subtype}')
        mon = self.data_type + 'mon'

        match self.data_type:
            case 'rad':
                for file in self.ctl_file:
                    self.logger.info(f'ctl file: {file}')
                    self.get_rad_datafile(self.pdate, file, dest_dir)
                for file in self.data_files:
                    for f in file:
                        date = os.path.basename(f).split(".")[2]
                        self.get_rad_datafile(date, f, dest_dir)

            case 'ozn':
                for file in self.ctl_file:
                    self.logger.info(f'ctl file: {file}')
                    self.get_ozn_datafile(self.pdate, file, dest_dir)
                for file in self.data_files:
                    for f in file:
                        date = os.path.basename(f).split(".")[2]
                        self.get_ozn_datafile(date, f, dest_dir)

            case 'min':
                for file in self.data_files:
                    for f in file:
                        if f == 'gnorm_data.txt':
                            date = self.pdate    
                        else:
                            date = os.path.basename(f).split(".")[0]
                        self.get_min_datafile(date, f, dest_dir)

            case 'con':
                for file in self.ctl_file:
                    self.get_con_datafile(self.pdate, file, dest_dir)

                for file in self.data_files:
                    for f in file:
                        date = os.path.basename(f).split(".")[1]
                        self.get_con_datafile(date, f, dest_dir)

            case _: 
                self.logger.info(f'unsupported case {self.data_type} in match self.data_type')

        for f in glob.glob(dest_dir + '/*.gz'):
            os.system(f'gunzip {f}')
