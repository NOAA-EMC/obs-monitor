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

        logger.info(f'cwd: {os.getcwd()}')

        self.pdate = datetime.strftime(config.get('PDATE'), '%Y%m%d%H')
        self.data_src = data_src
        self.logger = logger
        self.data_dir_type = ""
        self.plot_dict = {}
        self.ctl_file = None
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
        self.logger.info(f'    plot_dict: {self.plot_dict}')

        self.logger.info('end dump OM_data')
        self.logger.info('=== ==== =======')
        self.logger.info('')


# --------------------------------------------------------------------------------------------
    def set_data_types(self, template):
    
        self.data_type = template[:3].lower()
        stype = template[3:].lower() 
        self.logger.info(f'self.data_type: {self.data_type}')

        # summary will have to point to time, min type doesn't have a subtype
        if stype == 'summary' and self.data_type != 'min':
            stype = 'time'
        self.data_subtype = stype
        self.logger.info(f'self.data_subtype: {self.data_subtype}')

        if self.data_type == 'ozn':
            self.use_subtype = True

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

        #  Note it's possible to have more than 1 dataset so this will need to iterate
        #  is that really so?  Do any of the plot tempates have more than one dataset?  Maybe
        #  we just need to accept our limitations.
        ds = self.plot_dict.get('datasets')
        ds = ds[0]

        if 'control_file' in ds.keys():
            self.ctl_file = os.path.basename(ds['control_file'][0])
        self.data_files = [os.path.basename(f) for f in ds['filenames']]

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
        self.logger.info(f'self.data_src: {self.data_src}')
        self.logger.info(f'self.data_type: {self.data_type}')

        mon = self.data_type + 'mon'
        om_test = os.path.join(self.data_src, self.data_type + '_data')
        gw_test = ""
        go_test = "" 
        lm_test = ""

        match mon:
            case 'oznmon':
                # 'horiz' should be subtype, no?
                gw_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'products', 'atmos', mon, 'horiz', self.ctl_file)
                go_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'atmos', mon, 'horiz', self.ctl_file)
                lm_test = os.path.join(self.data_src, mon, 'stats', 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'horiz', self.ctl_file)

            case 'radmon':
                gw_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:],
                              'products', 'atmos', mon, 'radmon_' + self.data_subtype + '.tar.gz')
                go_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:],
                              'atmos', mon, 'radmon_' + self.data_subtype + '.tar.ga')
                lm_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                              'radmon', 'radmon_' + self.data_subtype + '.tar.gz')
                self.logger.info(f'lm_test: {lm_test}')

            case 'minmon':
                gw_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'products', 'atmos', mon)
                go_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'atmos', mon)
                lm_test = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], mon) 
                self.logger.info(f'lm_test: {lm_test}')
                     
        if os.path.exists(om_test):
            self.dir_struct = 'obs-mon'
        elif os.path.exists(gw_test):
            self.dir_struct = 'glb-wkflw'
        elif os.path.exists(go_test):
            self.dir_struct = 'gfs-ops'
        elif os.path.exists(lm_test):
            self.dir_struct = 'leg-mon'

# --------------------------------------------------------------------------------------------
    def copy_data(self, target_dir ):
        """
        Copy required data and control files to requested directory.

        Parameters:
            target_dir (path): directory to which data is to be copied
        Return:
            None
        """

        self.logger.info(f'target_dir: {target_dir}')
        self.logger.info(f'self.use_subtype: {self.use_subtype}')
        mon = self.data_type + 'mon'

        match self.dir_struct:
            case 'obs-mon':
                # tested on hera

                subtype = self.data_subtype if self.use_subtype else ""
                if self.ctl_file is not None:
                    src = os.path.join(self.data_src, self.data_type + '_data', subtype, self.ctl_file)
                    self.logger.info(f'src: {src}')

                    # this picks up a potentially gzipped ctl file
                    for f in glob.glob(src + '*'):
                        shutil.copy(f, target_dir)
                
                for file in self.data_files:
                    src = os.path.join(self.data_src, self.data_type + '_data', subtype, file)
                    self.logger.info(f'src: {src}')

                    # this picks up a potentially gzipped file
                    for f in glob.glob(src + '*'):
                        shutil.copy(f, target_dir)
                        
            case 'glb-wkflw':
                subtype = self.data_subtype if self.use_subtype else ""
                self.logger.info(f'glb-wkflw, subtype: {subtype}')

                if self.data_type == 'rad':
                    # tested on hera

                    # locate tar file
                    tarfile = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:],
                                              'products', 'atmos', mon, 'radmon_' + self.data_subtype + '.tar.gz')
                    self.logger.info(f' tarfile: {tarfile}')

                    cmd = 'tar -xf ' + tarfile + ' -C ' + target_dir + ' ' + self.ctl_file + '.gz'
                    self.logger.info(f' cmd: {cmd}')
                    os.system(cmd)

                    for file in self.data_files:
                        date = os.path.basename(file).split(".")[2]
                        pdy = date[:-2]
                        hh = date[-2:]

                        tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', mon,
                                                  'radmon_' + self.data_subtype + '.tar.gz')
                        cmd = 'tar -xf ' + tarfile + ' -C ' + target_dir + ' ' + file + '.gz'
                        self.logger.info(f' cmd: {cmd}')
                        os.system(cmd)

                elif self.data_type == 'min':
                    if self.ctl_file is not None:
                        src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                               'products', 'atmos', mon, self.ctl_file)
                        self.logger.info(f'src: {src}')
                        # This picks up a potentially gzipped ctl file.
                        # This could be a method().
                        for f in glob.glob(src + '*'):
                            shutil.copy(f, target_dir)

                    for file in self.data_files:
                        self.logger.info(f'file: {file}')
                        if file == 'gnorm_data.txt':
                            date = self.pdate
                        else:
                            date = os.path.basename(file).split(".")[0]
                        pdy = date[:-2]
                        hh = date[-2:]

                        fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', mon, file)
                        # this picks up a potentially gzipped file
                        for f in glob.glob(fsrc + '*'):
                            shutil.copy(f, target_dir)

                else:
                    # tested on hera

                    src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                               'products', 'atmos', mon, subtype, self.ctl_file)
                    self.logger.info(f' src: {src}')

                    # This picks up a potentially gzipped ctl file.
                    # This could be a method().
                    for f in glob.glob(src + '*'):
                        shutil.copy(f, target_dir)

                    for file in self.data_files:
                        date = os.path.basename(file).split(".")[2]
                        pdy = date[:-2]
                        hh = date[-2:]

                        fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'products', 'atmos', mon, subtype, fname)
                        # this picks up a potentially gzipped file
                        for f in glob.glob(fsrc + '*'):
                            shutil.copy(f, target_dir)

            case 'gfs-ops':
                subtype = self.data_subtype if self.use_subtype else ""
                self.logger.info(f'gfs-ops, subtype: {subtype}')

                # This will have to be tested on wcoss2.  I don't have rad data in gfs-ops form on hera.
                #
                if self.data_type == 'rad':
                    # locate tar file
                    tarfile = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:],
                                               'atmos', mon, 'radmon_' + self.data_subtype + '.tar.gz')
                    self.logger.info(f' tarfile: {tarfile}')

                    cmd = 'tar -xf ' + tarfile + ' -C ' + target_dir + ' ' + self.ctl_file + '.gz'
                    self.logger.info(f' cmd: {cmd}')
                    os.system(cmd)

                    for file in self.data_files:
                        date = os.path.basename(file).split(".")[2]
                        pdy = date[:-2]
                        hh = date[-2:]

                        tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', mon, 'radmon_' + self.data_subtype + '.tar.gz')
                        cmd = 'tar -xf ' + tarfile + ' -C ' + target_dir + ' ' + file + '.gz'
                        self.logger.info(f' cmd: {cmd}')
                        os.system(cmd)

                elif self.data_type == 'min': 
                    self.logger.info('case gfs-ops, min')
                    if self.ctl_file is not None:
                        src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 
                                               'atmos', mon, self.ctl_file)
                        self.logger.info(f'src: {src}')
                        # This picks up a potentially gzipped ctl file.
                        # This could be a method().
                        for f in glob.glob(src + '*'):
                            shutil.copy(f, target_dir)

                    for file in self.data_files:
                        self.logger.info(f'file: {file}')
                        if file == 'gnorm_data.txt':
                            date = self.pdate
                        else:
                            date = os.path.basename(file).split(".")[0]
                        pdy = date[:-2]
                        hh = date[-2:]

                        fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', mon, file)
                        # this picks up a potentially gzipped file
                        for f in glob.glob(fsrc + '*'):
                            shutil.copy(f, target_dir)


                else: 
                    # tested on hera

                    src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], 'atmos', mon, subtype, self.ctl_file)
                    # This picks up a potentially gzipped ctl file.
                    # This could be a method().
                    for f in glob.glob(src + '*'):
                        shutil.copy(f, target_dir)

                    for file in self.data_files:
                        fname = os.path.basename(file)
                        date = fname.split(".")[2]
                        pdy = date[:-2]
                        hh = date[-2:]

                        if self.use_subtype:
                            fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', mon, self.data_subtype, fname)
                        else:
                            fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, 'atmos', mon, fname)

                        # this picks up a potentially gzipped file
                        for f in glob.glob(fsrc + '*'):
                            shutil.copy(f, target_dir)

            case 'leg-mon':
                self.logger.info(f'identified leg-mon case: {self.dir_struct}')
                mon = self.data_type + 'mon'
                self.logger.info(f' mon: {mon}')
 
                if self.data_type == 'rad':
                    # test on wcoss2
                    self.logger.info(f'case rad identified')
                    tarfile = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], mon,
                                               'radmon_' + self.data_subtype + '.tar.gz')
                    self.logger.info(f' tarfile: {tarfile}')

                    if os.path.exists(tarfile):
                        cmd = 'tar -xf ' + tarfile + ' -C ' + target_dir + ' ' + self.ctl_file + '.gz'
                        self.logger.info(f' cmd: {cmd}')
                        os.system(cmd)

                    for file in self.data_files:
                        date = os.path.basename(file).split(".")[2]
                        pdy = date[:-2]
                        hh = date[-2:]

                        tarfile = os.path.join(self.data_src, 'gdas.' + pdy, hh, mon, 'radmon_' + self.data_subtype + '.tar.gz')
                        if os.path.exists(tarfile):
                            cmd = 'tar -xf ' + tarfile + ' -C ' + target_dir + ' ' + file + '.gz'
                            self.logger.info(f' cmd: {cmd}')
                            os.system(cmd)

                elif self.data_type == 'min': 
                    self.logger.info('case gfs-ops, min')
                    if self.ctl_file is not None:
                        src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], mon, self.ctl_file)
                        self.logger.info(f'src: {src}')
                        # This picks up a potentially gzipped ctl file.
                        # This could be a method().
                        for f in glob.glob(src + '*'):
                            shutil.copy(f, target_dir)

                    for file in self.data_files:
                        self.logger.info(f'file: {file}')
                        if file == 'gnorm_data.txt':
                            date = self.pdate
                        else:
                            date = os.path.basename(file).split(".")[0]
                        pdy = date[:-2]
                        hh = date[-2:]

                        fsrc = os.path.join(self.data_src, 'gdas.' + pdy, hh, mon, file)
                        # this picks up a potentially gzipped file
                        for f in glob.glob(fsrc + '*'):
                            shutil.copy(f, target_dir)

                else:
                    # fix ozn data and retest on hera
                    subtype = self.data_subtype if self.use_subtype else ""
                    src = os.path.join(self.data_src, 'gdas.' + self.pdate[:-2], self.pdate[-2:], mon, self.data_subtype, self.ctl_file)
                    self.logger.info(f'src: {src}') 
                    # This picks up a potentially gzipped ctl file.
                    # This could be a method().
                    for f in glob.glob(src + '*'):
                        shutil.copy(f, target_dir)

                    for file in self.data_files:
                        fname = os.path.basename(file)
                        date = fname.split(".")[2]
                        pdy = date[:-2]
                        hh = date[-2:]
    
                        if self.use_subtype:
                            fsrc = os.path.join(self.data_src, mon, 'stats', 'gdas.' + pdy, hh, self.data_subtype, fname)
                        else:
                            fsrc = os.path.join(self.data_src, mon, 'stats', 'gdas.' + pdy, hh, fname)
                        self.logger.info(f'fsrc: {fsrc}')

                        # this picks up a potentially gzipped file
                        for f in glob.glob(fsrc + '*'):
                            shutil.copy(f, target_dir)

            case _:
                self.logger.info(f'no match on dir_struct {self.dir_struct}')

        for f in glob.glob(target_dir + '/*.gz'):
            os.system(f'gunzip {f}')
