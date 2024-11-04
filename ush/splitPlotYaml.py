#!/usr/bin/env python3
# splitPlotYaml
#
# Parse input yaml plot file, break it into smaller yaml files
# by satellite/instrument and for larger instruments, plot type.

import argparse
import yaml
from eva.utilities.logger import Logger


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


def check_plotlist(type, logger, plot_list, sat=None, instr=None):
    """
    """
    logger.info(f'--> check_plotlist')
    sat_reqs = {'rad': ['plot', 'times', 'channels', 'component', 'run'], 
                'ozn': ['plot', 'times', 'levels', 'component', 'run']} 

    rtn_val = True
    missing = []
    match type:
            case 'sat':   
                if 'rad' in plot_list.get('plot'):
                    reqs = sat_reqs.get('rad')
                else:
                    reqs = sat_reqs.get('ozn')

                for val in reqs:
                    if val not in plot_list:
                        missing.append(val) 
                        plot_str = (f" {instr} {sat} {plot_list.get('plot')}")         

#           case 'min':   
#           case 'obs':   
#           cast _:

    if missing:
        logger.info(f'WARNING:  YAML for plot {plot_str}  is missing  {missing}')
        logger.info(f'WARNING:  Requested plot will be SKIPPED.')
        rtn_val = False
 
    return (rtn_val)
    logger.info(f'<-- check_plotlist')


if __name__ == "__main__":
    """
    splitPlotYaml

    Read and parse input plot and channel data yaml files.  Extract the satellite data,
    evaluate the number of channels for a given instrument and then create smaller yaml plot
    files spliting by satellite/instrument or satellite/instrument/plot and keeping all
    the additional data (model name, time interval, etc).

    Example calling sequence: >python splitPlotYaml.py -i ../parm/gfs/gfs_plots.yaml
                                  -c ../parm/instrument_channels.py
    """

    logger = Logger('splitPlotYaml')
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', type=str, help='Input YAML plot file', required=True)
    parser.add_argument('-c', '--chan', type=str,
                        help='Input YAML instrument channel file', required=True)
    args = parser.parse_args()

    try:
        mon_sources = args.input
        with open(mon_sources, 'r') as mon_sources_opened:
            mon_dict = yaml.safe_load(mon_sources_opened)
    except Exception as e:
        logger.abort('splitPlotYaml is expecting a valid model plot yaml file, but encountered ' +
                     f'errors when attempting to load: {mon_sources}, error: {e}')

    try:
        chan_data = args.chan
        with open(chan_data, 'r') as chan_data_opened:
            chan_dict = yaml.safe_load(chan_data_opened)
    except Exception as e:
        logger.abort('splitPlotYaml is expecting a valid satellite channel file, but encountered ' +
                     f'errors when attempting to load: {chan_data}, error: {e}')

    model = mon_dict.get('model')
    cycle_interval = mon_dict.get('cycle_interval')
    data = mon_dict.get('data')

    if 'satellites' in mon_dict.keys():
        logger.info(f' split_plot, in satellites')
        sd = removeKey(mon_dict, ['minimization', 'observations'])

        for sat in mon_dict.get('satellites'):
            satname = sat.get('name')

            for inst in sat.get('instruments'):
                iname = inst.get('name')
                plist = inst.get('plot_list')
                for pl in inst.get('plot_list'):
                    if not check_plotlist('sat', logger, pl, sat=satname, instr=iname):
                        continue

                # --------------------------------------------------------------------
                # For instruments with a large number of channels split the plot_list
                #
                channels = chan_dict.get(iname)
                logger.info(f' channels: {channels}')
                nchans = 0
                if channels is not None:
                    nchans = len(channels.split(","))
                logger.info(f' nchans: {nchans}')

                if nchans > 100:
                    ctr = 0
                    for pl in inst.get('plot_list'):
                        pd = sd
                        pd['satellites'] = [{'name': satname,
                                             'instruments': [{'name': iname,
                                                              'plot_list': [pl]}]}]
                        fname = f'OM_PLOT_sat_{satname}_{iname}_{ctr}.yaml'
                        file = open(fname, "w")
                        yaml.dump(pd, file)
                        file.close()
                        ctr += 1

                else:
                    pd = sd
                    pd['satellites'] = [{'name': satname,
                                         'instruments': [{'name': iname,
                                                          'plot_list': plist}]}]
                    fname = f'OM_PLOT_sat_{satname}_{iname}.yaml'
                    file = open(fname, "w")
                    yaml.dump(pd, file)
                    file.close()

    if 'minimization' in mon_dict.keys():
        md = removeKey(mon_dict, ['satellites', 'observations'])
        fname = f'OM_PLOT_minimization.yaml'
        mm = md.get('minimization')
        logger.info(f'mm: {mm}')
        for m in mm.get('plot_list'):
            logger.info(f'm: {m}')

        file = open(fname, "w")
        yaml.dump(md, file)
        file.close()

    if 'observations' in mon_dict.keys():
        od = removeKey(mon_dict, ['satellites', 'minimization'])
        fname = f'OM_PLOT_observations.yaml'
        file = open(fname, "w")
        yaml.dump(od, file)
        file.close()
