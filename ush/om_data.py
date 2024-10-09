#import yaml
import os
import shutil
import glob
import pprint

from datetime import datetime
from eva.utilities.logger import Logger
from wxflow import parse_yaml

class OM_data:
    """
    Class to manage legacy obs-mon data and prepare it for plotting.
    """

    def __init__(self, data_src, config, plot_yaml, logger):
        """
        Initialize OM_data object and copy data to requested location.
        """

        self.pdate = datetime.strftime(config.get('PDATE'), '%Y%m%d%H')
        self.data_src = data_src
        self.logger = logger
        self.data_dir_type = ""
        self.ctl_file = []
        self.data_files = []
        self.dir_struct = ""
        self.data_type = ""
        self.data_subtype = ""
        self.run = config.get('RUN')

        self.load_data_files(plot_yaml)
        self.set_data_types(os.path.basename(config.get('PLOT_TEMPLATE')))
        self.set_dir_struct()

        self.copy_data(os.getcwd())
        self.dump()

# --------------------------------------------------------------------------------------------

    def dump(self):
        """
        Dump all current values in object of class OM_data via logger.info.

        Paremeters:
            None
        Return:
            None
        """

        pp = pprint.PrettyPrinter(indent=4)
        self.logger.info(f'\n' + 'dump OM_data:')
        self.logger.info('============')
        pp.pprint(vars(self))
        self.logger.info('============' + '\n')
# --------------------------------------------------------------------------------------------

    def set_data_types(self, template):
        """
        Set data_type and data_subtype using the plot template name.  Note
        that 'con' and 'ozn' types have some special cases for subtype.

        Paremeters:
            template (str): Name of plot template file
        Return:
            None
        """

        self.data_type = template[:3].lower()
        stype = template[3:].lower()

        if self.data_type == 'con':
            if stype in ['time', 'vert']:
                self.data_subtype = 'time_vert'
            elif stype in ['hist', 'horz']:
                self.data_subtype = 'horz_hist'

        elif self.data_type == 'ozn' and stype == 'summary':
                self.data_subtype = 'time'

        else:
            self.data_subtype = stype

# --------------------------------------------------------------------------------------------

    def load_data_files(self, yaml_file):

        """
        Load control and data file names from yaml_file into OM_data class object.

        Parameters:
            yaml_file (file): yaml file with plot dict info
        Return:
            None
        """

        try:
            pd = parse_yaml(path=yaml_file)
            for d in pd.get('datasets'):
                if 'control_file' in d.keys():
                    self.ctl_file.append(os.path.basename(d['control_file'][0]))
                self.data_files.append([os.path.basename(f) for f in d['filenames']])

        except Exception as e:
            self.logger.info('Warning: unable to load yaml file into dict, ' +
                             f'errors when attempting to load: {yaml_file}, error: {e}')

# --------------------------------------------------------------------------------------------

    def set_dir_struct(self):
        """
        Determine which data directory structure is in use. Supported structures are:
            obs-mon:   used for development, data is simply in 'ozn_data', 'rad_data', etc.
                       and is not gzipped or tarred.
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

        base_path = os.path.join(self.data_src, self.run + '.' + self.pdate[:-2], self.pdate[-2:])

        match mon:
            case 'oznmon':
                gw_test = os.path.join(base_path, 'products', 'atmos', mon, self.data_subtype)
                go_test = os.path.join(base_path, 'atmos', mon, self.data_subtype)
                lm_test = os.path.join(base_path, mon, self.data_subtype)

            case 'radmon':
                tar_file = mon + '_' + self.data_subtype + '.tar.gz'
                gw_test = os.path.join(base_path, 'products', 'atmos', mon, tar_file)
                go_test = os.path.join(base_path, 'atmos', mon, tar_file)
                lm_test = os.path.join(base_path, mon, tar_file)

            case 'minmon':
                gw_test = os.path.join(base_path, 'products', 'atmos', mon)
                go_test = os.path.join(base_path, 'atmos', mon)
                lm_test = os.path.join(base_path, mon)

            # conmon is only in obs-mon and leg-mon structures
            case 'conmon':
                # rm ctl file?
                lm_test = os.path.join(base_path, mon, self.data_subtype, self.ctl_file[0])

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
        Locate and copy file to dest_dir.

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

        base_path = os.path.join(self.data_src, self.run + '.' + cycle[:-2], cycle[-2:])

        match self.dir_struct:
            case 'obs-mon':
                tarfile = ""
                f = os.path.join(self.data_src, 'rad_data', file)
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)

            case 'glb-wkflw':
                tarfile = os.path.join(base_path, 'products', 'atmos', 'radmon',
                                       'radmon_' + self.data_subtype + '.tar.gz')
            case 'gfs-ops':
                tarfile = os.path.join(base_path, 'atmos', 'radmon', 'radmon_' +
                                       self.data_subtype + '.tar.gz')
            case 'leg-mon':
                tarfile = os.path.join(base_path, 'radmon', 'radmon_' + self.data_subtype +
                                       '.tar.gz')

        if os.path.isfile(tarfile):
            os.system('tar -xf ' + tarfile + ' -C ' + dest_dir + ' --wildcards ' + file + '*')

# --------------------------------------------------------------------------------------------

    def get_ozn_datafile(self, cycle, file, dest_dir):

        """
        Locate and copy file to dest_dir.

        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name
            dest_dir (path):  full directory path to where data file is to be extracted.
        Return:
            None

        """

        base_path = os.path.join(self.data_src, self.run + '.' + cycle[:-2], cycle[-2:])

        match self.dir_struct:
            case 'obs-mon':
                f = os.path.join(self.data_src, 'ozn_data', self.data_subtype, file)
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)
            case 'glb-wkflw':
                ff = os.path.join(base_path, 'products',
                                  'atmos', 'oznmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
            case 'gfs-ops':
                ff = os.path.join(base_path, 'atmos', 'oznmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
            case 'leg-mon':
                ff = os.path.join(base_path, 'oznmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)

# --------------------------------------------------------------------------------------------

    def get_min_datafile(self, cycle, file, dest_dir):

        """
        Locate and copy file to dest_dir.

        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name
            dest_dir (path):  full directory path to where data file is to be extracted.
        Return:
            None

        """

        base_path = os.path.join(self.data_src, self.run + '.' + cycle[:-2], cycle[-2:])

        match self.dir_struct:
            case 'obs-mon':
                f = os.path.join(self.data_src, 'min_data', file)
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)
            case 'glb-wkflw':
                ff = os.path.join(base_path, 'products', 'atmos', 'minmon', file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
            case 'gfs-ops':
                ff = os.path.join(base_path, 'atmos', 'minmon', file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)
            case 'leg-mon':
                ff = os.path.join(base_path, 'minmon', file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)

# --------------------------------------------------------------------------------------------

    def get_con_datafile(self, cycle, file, dest_dir):

        """
        Locate and copy file to dest_dir.

        Parameters:
            cycle (str):   cycle time (in YYYYMMDDHH format) of the requested tar file
            file (str):    data file name
            dest_dir (path):  full directory path to where data file is to be extracted.
        Return:
            None

        """

        self.logger.info(f'--> get_con_dataile, cycle: {cycle}, file: {file}')

        base_path = os.path.join(self.data_src, self.run + '.' + cycle[:-2], cycle[-2:])

        match self.dir_struct:
            case 'obs-mon':
                f = os.path.join(self.data_src, 'con_data', self.data_subtype, file)
                self.logger.info(f'obs-mon case, f: {f}')
                if os.path.isfile(f):
                    shutil.copy(f, dest_dir)
            case 'glb-wkflw':
                self.logger.info(f'case glb-wkflw not yet supported')
            case 'gfs-ops':
                self.logger.info(f'case gfs-ops not yet supported')
            case 'leg-mon':
                ff = os.path.join(base_path, 'conmon', self.data_subtype, file)
                for f in glob.glob(ff + '*'):
                    shutil.copy(f, dest_dir)

# --------------------------------------------------------------------------------------------

    def copy_data(self, dest_dir):
        """
        Copy required data and control files to requested directory.

        Parameters:
            dest_dir (path): directory to which data is to be copied
        Return:
            None
        """

        mon = self.data_type + 'mon'

        match self.data_type:
            case 'rad':
                for file in self.ctl_file:
                    self.get_rad_datafile(self.pdate, file, dest_dir)
                for file in self.data_files:
                    for f in file:
                        date = os.path.basename(f).split(".")[2]
                        self.get_rad_datafile(date, f, dest_dir)

            case 'ozn':
                for file in self.ctl_file:
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
