
import argparse
import yaml
import os
from re import sub
from datetime import datetime
from eva.utilities.logger import Logger
from wxflow import add_to_datetime, to_timedelta, to_datetime

# --------------------------------------------------------------------------------------------
def removeKey(d, keys):
    """
    Remove keys from a dictionary

    Parameters:
        d (dict): input dictionary
        keys (list): keys to remove from dictionary

    Return:
        modified dictionary if key(s) are found or input dictionary if no keys
        are in input dictionary
    """

    r = dict(d)
    for key in keys:
        if key in d.keys():
            del r[key]
    return r

# --------------------------------------------------------------------------------------------
def camelCase(s):
    """
    Convert string with spaces, dashes, or underscores to cammel case.

    Parameters:
        s (str): input string
    Return:
        string contents in camelCase
    """
    
    s = sub(r"(_|-)+", " ", s).title().replace(" ", "")
    return ''.join([s[0].lower(), s[1:]])

# --------------------------------------------------------------------------------------------
def get_cycles(pdate, logger, cycle_interval=6, max_cycles=121):
    """
    Create a list of processing dates starting from input pdate to max_cycles * cycle_interval

    Parameters:
        pdate (string): first processing date in YYYYMMDDHH format
        logger:

    Return:
        list of cycle times 
    """

    cycle_tm = to_datetime(pdate)
    cycles = [pdate]
    for x in range(1, max_cycles):
        new_date = add_to_datetime(cycle_tm, to_timedelta(f"-{cycle_interval*x}H"))
        cycles.append(datetime.strftime(new_date, "%Y%m%d%H"))
        
    return cycles

# --------------------------------------------------------------------------------------------


def setupdata(config, logger):
    """
    Read in config and set up required data files locall.

    Parameters:
        config (dict): dictionary of plot information
    Return:
        None
    """

    logger.info(f'--> setUpData')
    logger.info(f' config: {config}')

    workspace = os.environ.get('DATA', '.')
    path = os.path.join(workspace, "ozn_data")
    os.mkdir(path, exist_ok=True)

    logger.info(f'<-- setUpData')

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

#   model = mon_dict.get('model')
#   data = mon_dict.get('data')
#   logger.info(f'model: {model}')
#   logger.info(f'data: {data}')

#   # Create data directories in workspace, using env var $DATA
#   workspace = os.environ.get('DATA', '.')
#   os.chdir(workspace)
#   dir_list = ['con_data', 'mon_data', 'ozn_data/horz', 'ozn_data/time', 'rad_data']
#
#   for dir in dir_list:
#       path = os.path.join(workspace, dir)
#       os.makedirs(path, exist_ok=True)
#
#   if 'satellites' in mon_dict.keys():
#       for sat in mon_dict.get('satellites'):
#           satname = sat.get('name')

#           for inst in sat.get('instruments'):
#               iname = inst.get('name')
#               logger.info(f'satname: {satname}, instrument: {iname}')
#              
#               ozn_instruments = ['gome', 'omi', 'ompslp', 'ompsnp', 'ompstc8']

#               if iname in ozn_instruments:
#                   logger.info(f'{iname} is OZN')
#                   plist = inst.get('plot_list')
#                   logger.info(f'plist: {plist}')
#                   for p in range (len(plist)):
#                       logger.info(f'plist[p]: {plist[p]}')
#                        plt=plist[p].get('plot')
#                       plt=camelCase(plist[p].get('plot'))
#                       logger.info(f'plt: {plt}')
 
#               else:
#                   logger.info(f'{iname} is RAD')



                # --------------------------------------------------------------------
                # For instruments with a large number of channels split the plot_list
                #
#               channels = chan_dict.get(iname)
#               nchans = 0
#               if channels is not None:
#                   nchans = len(channels.split(","))

#               if nchans > 100:
#                   ctr = 0
#                   for pl in inst.get('plot_list'):
#                       pd = sd
#                       pd['satellites'] = [{'name': satname,
#                                            'instruments': [{'name': iname,
#                                                             'plot_list': [pl]}]}]
#                       fname = f'OM_PLOT_sat_{satname}_{iname}_{ctr}.yaml'
#                       file = open(fname, "w")
#                       yaml.dump(pd, file)
#                       file.close()
#                       ctr += 1

#               else:
#                   pd = sd
#                   pd['satellites'] = [{'name': satname,
#                                        'instruments': [{'name': iname,
#                                                         'plot_list': plist}]}]
#                   fname = f'OM_PLOT_sat_{satname}_{iname}.yaml'
#                   file = open(fname, "w")
#                   yaml.dump(pd, file)
#                   file.close()

#   if 'minimization' in mon_dict.keys():
#       md = removeKey(mon_dict, ['satellites', 'observations'])
#       fname = f'OM_PLOT_minimization.yaml'
#       file = open(fname, "w")
#       yaml.dump(md, file)
#       file.close()
#
#   if 'observations' in mon_dict.keys():
#       od = removeKey(mon_dict, ['satellites', 'minimization'])
#       fname = f'OM_PLOT_observations.yaml'
#       file = open(fname, "w")
#       yaml.dump(od, file)
#       file.close()
