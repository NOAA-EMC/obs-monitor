#!/usr/bin/env python
from solo.configuration import Configuration
from solo.basic_files import mkdir
import htmlhelpers.rad as htmlrad
import htmlhelpers.common as htmlc
import sys
import os

config = Configuration(sys.argv[1])

# generate radiance homepage
htmlrad.gen_rad_home(config)

# loop through radiance obs
for rad in config.radiances:
    try:
        # generate individual radiance homepages
        htmlrad.gen_sensor_home(rad, config)
        # generate their 'view' pages
        htmlrad.gen_sensor_view(rad, config)
    except:
        pass

# copy css and js files
htmlc.copy_css_js(config)
