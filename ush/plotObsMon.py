#!/usr/bin/env python3
# plotObsMon
#
# Parse input yaml plot file, apply to DA monitor templates to
# create eva yaml files, run eva.

import argparse
import os
from re import sub
import yaml
from wxflow import parse_j2yaml, save_as_yaml
from wxflow import add_to_datetime, to_timedelta, to_datetime
from eva.eva_driver import eva
from eva.utilities.logger import Logger


def genYaml(input_yaml, output_yaml, config):
    """
    Read in input yaml file and modify with contents of config.

    Parameters:
        input_yaml (yaml file): path to input yaml file
        output_yaml (yaml file): path to output yaml file
        config (dict): configuration dictionary
    Return:
        None
    """

    final_config = parse_j2yaml(input_yaml, config)
    save_as_yaml(final_config, output_yaml)

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


def loadConfig(satname, instrument, obstype, plot, cycle_tm, cycle_interval,
               data_location, model=None):
    """
    Load configuration dictionary.

    Parameters:
        satname (str): Name of satellite
        instrument (str): Name of instrument
        obstype (str): Type of observation
        plot (str): plot template
        cycle_tm (datetime): Cycle time of plot
        cycle_interval (int): number of hours between cycles
        data_location (str): path to directory containing data files
        model (str): model|experiment name
    Return:
        config(dict): Dictionary containing configuration information
    """
    config = {
        'SAT': satname,
        'SENSOR': instrument,
        'OBSTYPE': obstype,
        'LEVELS': plot.get('levels'),
        'CHANNELS': plot.get('channels'),
        'MODEL': model,
        'RUN': plot.get('run'),
        'COMPONENT': plot.get('component'),
        'PDATE': cycle_tm,
        'PLOT_TEMPLATE': camelCase(plot.get('plot')),
        'DATA': data_location
    }

    times = int(plot.get('times')) if plot.get('times') else None
    if times is not None:
        for x in range(1, times+1):
            date_str = f"PDATEm{x*cycle_interval}"
            config[date_str] = add_to_datetime(cycle_tm, to_timedelta(f"-{cycle_interval*x}H"))

    # Some plots with channels require a configuration value of XTICKS (tick marks on the
    # plotted x axis).  The x axis tick marks indicate the actual channel number, which can
    # be > 8000 for iasi.  Use the actual channel numbers as tick marks, if the last channel
    # is < 30 (all but cris-fsr and iasis are), or use a resonable interval if larger.
    if config['CHANNELS'] is not None:
        last_chan = int(config['CHANNELS'].split(',')[-1])

        if last_chan < 30:
            config['XTICKS'] = config['CHANNELS']
        else:
            interval = 250 if last_chan < 3000 else 1000
            ctr = interval
            xticks = ""
            while ctr < int(last_chan):
                xticks = xticks + str(ctr) + ','
                ctr += interval
            config['XTICKS'] = xticks[:-1]

    return config

# --------------------------------------------------------------------------------------------


if __name__ == "__main__":
    """
    plotObsMon

    Read and parse input yaml file, load configuration and apply to requested yaml template(s),
    and plot results.

    Example calling sequence: >python plotObsMon.py -i ../parm/gfs/gfs_plots.yaml -p 2023122000
    """

    logger = Logger('plotObsMon')
    parser = argparse.ArgumentParser()

    parser.add_argument('-i', '--input', type=str, help='Input YAML plot file', required=True)
    parser.add_argument('-p', '--pdate', type=str, help='Plot time YYYYMMDDHH', required=True)
    args = parser.parse_args()
    cycle_tm = to_datetime(args.pdate)

    try:
        mon_sources = args.input
        with open(mon_sources, 'r') as mon_sources_opened:
            mon_dict = yaml.safe_load(mon_sources_opened)
    except Exception as e:
        logger.abort('plotObsMon is expecting a valid yaml file, but it encountered ' +
                     f'errors when attempting to load: {mon_sources}, error: {e}')

    model = mon_dict.get('model')
    cycle_interval = mon_dict.get('cycle_interval')
    data_location = mon_dict.get('data')

    # Generate template YAMLS and figures for specified satellite instruments
    # minimization stats, and conventional observations
    if 'satellites' in mon_dict.keys():
        for sat in mon_dict.get('satellites'):
            satname = sat.get('name')
            obstype = None

            for inst in sat.get('instruments'):
                instrument = inst.get('name')

                for plot in inst.get('plot_list'):
                    config = loadConfig(satname, instrument, obstype, plot, cycle_tm,
                                        cycle_interval, data_location, model)
                    plot_template = f"{config['PLOT_TEMPLATE']}.yaml"
                    plot_yaml = f"{config['SENSOR']}_{config['SAT']}_{plot_template}"

                    parm = os.environ.get('PARMobsmon', '../parm')
                    parm_location = os.path.join(parm, model)
                    plot_template = os.path.join(parm_location, plot_template)

                    genYaml(plot_template, plot_yaml, config)

                    eva(plot_yaml)
                    os.remove(plot_yaml)

    if 'minimization' in mon_dict.keys():
        satname = None
        instrument = None
        obstype = None

        for min in mon_dict.get('minimization'):
            model = min.get('model')

            for plot in min.get('plot_list'):
                config = loadConfig(satname, instrument, obstype, plot, cycle_tm, cycle_interval,
                                    data_location, model)

                plot_template = f"{config['PLOT_TEMPLATE']}.yaml"
                plot_yaml = f"{config['MODEL']}_{config['RUN']}_{plot_template}"

                parm = os.environ.get('PARMobsmon', '../parm')
                parm_location = os.path.join(parm, model)
                plot_template = os.path.join(parm_location, plot_template)

                genYaml(plot_template, plot_yaml, config)
                eva(plot_yaml)
                os.remove(plot_yaml)

    if 'observations' in mon_dict.keys():
        satname = None
        instrument = None
        obstype = None
        for obs in mon_dict.get('observations'):
            obstype = obs.get('obstype')

            for plot in obs.get('plot_list'):
                config = loadConfig(satname, instrument, obstype, plot, cycle_tm, cycle_interval,
                                    data_location)

                plot_template = f"{config['PLOT_TEMPLATE']}.yaml"
                plot_yaml = f"{config['OBSTYPE']}_{plot_template}"
                   
                parm = os.environ.get('PARMobsmon', '../parm')
                parm_location = os.path.join(parm, model)
                plot_template = os.path.join(parm_location, plot_template)

                genYaml(plot_template, plot_yaml, config)
                eva(plot_yaml)
                os.remove(plot_yaml)
