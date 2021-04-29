from solo.configuration import Configuration
from solo.basic_files import mkdir
import os
import htmlhelpers.common as htmlc
import glob

def gen_rad_home_lists(radlist):
    # generate HTML strings of links to all radiance obs
    # defined in the configuration
    linkstr = ''
    btnstr = ''
    sensors = {}
    # create div for each sensor/platform combo
    for rad in radlist:
        type = rad['name'].split('_')[0]
        link = f'{rad["name"]}/index.html'
        label = rad['fullname']
        linkstr = linkstr + f'<div class="filterDiv {type}"><a href="{link}" class="w3-bar-item w3-button w3-padding">{label}</a></div>\n'
        sensor_name = label.split()[0]
        if sensor_name not in sensors.keys():
            sensors[sensor_name] = type
    # create buttons to filter but just by sensor
    for name, type in sensors.items():
        btnstr = btnstr + f'<button class="btn w3-white" onclick="filterSelection(\'{type}\')">{name}</button>'
    return btnstr, linkstr

def gen_sensor_html(rad, config):
    # generate HTML strings based off of available figures for this sensor
    imgstr = ''
    btnstr = ''
    # figure out most recent cycle
    cycledirs = sorted(glob.glob(os.path.join(config.root_fig, '20*')))
    cycledir = cycledirs[-1]
    cycle = os.path.basename(cycledir)
    # scatter plots for individual cycles
    btnstr = btnstr + f'<button class="btn w3-white" onclick="filterSelection(\'scatter\')">Scatter</button>'
    # get all scatter plots for newest cycle
    scatterfigs = glob.glob(os.path.join(cycledir, rad['name'], '*_scatter.png'))
    # TODO sort by channel, maybe easier to save figure with leading zeros?
    # TODO put below loops into a function since most is repeated
    figrelpath = f'../../figs/{cycle}/{rad["name"]}/'
    for sfig in scatterfigs:
        # get name
        # TODO fix this later when figure names change
        sfig_name = ' '.join(os.path.basename(sfig).split('_')[2:-1])
        sfig_name = sfig_name.replace('brightness temperature', 'channel')
        link = figrelpath + os.path.basename(sfig) # replace later with next page but with POST for channel, cycle, etc.
        imgsrc = figrelpath + os.path.basename(sfig)
        imgstr = imgstr + f'<div class="btnimg filterDiv scatter"><a href="{link}"class="w3-bar-item w3-button w3-padding">{sfig_name}<img src="{imgsrc}"></a></div>\n'
    # non timeseries line plots
    btnstr = btnstr + f'<button class="btn w3-white" onclick="filterSelection(\'lineplt\')">Line</button>'
    linefigs = glob.glob(os.path.join(cycledir, rad['name'], '*_line.png'))
    # TODO sort by channel, maybe easier to save figure with leading zeros?
    for lfig in linefigs:
        # get name
        # TODO fix this later when figure names change
        lfig_name = ' '.join(os.path.basename(lfig).split('_')[2:-1])
        lfig_name = lfig_name.replace('brightness temperature', 'channel')
        link = figrelpath + os.path.basename(lfig) # replace later with next page but with POST for channel, cycle, etc.
        imgsrc = figrelpath + os.path.basename(lfig)
        imgstr = imgstr + f'<div class="btnimg filterDiv lineplt"><a href="{link}"class="w3-bar-item w3-button w3-padding">{lfig_name}<img src="{imgsrc}"></a></div>\n'
    return btnstr, imgstr

def get_includes_rad(roothref):
    # return strings of includes for CSS style and javascript
    cssstr = f'<link rel="stylesheet" href="{roothref}css/rad.css">'
    jsstr = f'<script type="text/javascript" src="{roothref}js/rad.js"></script>'
    return cssstr, jsstr

def gen_sensor_view(rad, config):
    # generate landing page for each sensor/platform combination
    # output html path
    htmldir = os.path.join(config.html_out, 'rad', rad['name'])
    mkdir(htmldir)
    htmlpath = os.path.join(htmldir, 'view.html')
    # get HTML of buttons and images to display
    sensorbtn, sensorimg = gen_sensor_html(rad, config)
    # get relative path for links
    roothref = htmlc.get_rootpath(config, htmlpath)
    # get includes of CSS and javascript
    cssstr, jsstr = get_includes_rad(roothref)
    strs = {}
    strs['{{PAGETITLE}}'] = rad['fullname']
    strs['{{FIGBTNLIST}}'] = sensorbtn
    strs['{{FIGLIST}}'] = sensorimg
    strs['{{ROOTPATH}}'] = roothref
    strs['{{CSSINCLUDE}}'] = cssstr
    strs['{{JSINCLUDE}}'] = jsstr
    # open the output file for writing
    with open(htmlpath, 'w') as hf:
        # need to open, replace, write several template files
        # top of page first
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'title.html'),
                   strs, hf)
        # nav bar
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'sidebar.html'),
                   strs, hf)
        # main page
        htmlc.write_html(os.path.join(config.html_in, 'rad', 'sensorview.html'),
                   strs, hf)
        # footer
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'footer.html'),
                   strs, hf)

def gen_sensor_home(rad, config):
    # generate landing page for each sensor/platform combination
    # output html path
    htmldir = os.path.join(config.html_out, 'rad', rad['name'])
    mkdir(htmldir)
    htmlpath = os.path.join(htmldir, 'index.html')
    # get HTML of buttons and images to display
    sensorbtn, sensorimg = gen_sensor_html(rad, config)
    # get relative path for links
    roothref = htmlc.get_rootpath(config, htmlpath)
    # get includes of CSS and javascript
    cssstr, jsstr = get_includes_rad(roothref)
    strs = {}
    strs['{{PAGETITLE}}'] = rad['fullname']
    strs['{{FIGBTNLIST}}'] = sensorbtn
    strs['{{FIGLIST}}'] = sensorimg
    strs['{{ROOTPATH}}'] = roothref
    strs['{{CSSINCLUDE}}'] = cssstr
    strs['{{JSINCLUDE}}'] = jsstr
    # open the output file for writing
    with open(htmlpath, 'w') as hf:
        # need to open, replace, write several template files
        # top of page first
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'title.html'),
                   strs, hf)
        # nav bar
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'sidebar.html'),
                   strs, hf)
        # main page
        htmlc.write_html(os.path.join(config.html_in, 'rad', 'sensorhome.html'),
                   strs, hf)
        # footer
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'footer.html'),
                   strs, hf)

def gen_rad_home(config):
    # generate radiance obs homepage
    # output HTML path
    htmlpath = os.path.join(config.html_out, 'rad', 'index.html')
    # get list of all radiance obs to display as links and create buttons to sort
    radhomebtn, radhomelist = gen_rad_home_lists(config.radiances)
    # get relative path for links
    roothref = htmlc.get_rootpath(config, htmlpath)
    # get includes of CSS and javascript
    cssstr, jsstr = get_includes_rad(roothref)
    strs = {}
    strs['{{PAGETITLE}}'] = 'Radiance Observations - Home'
    strs['{{SENSORBTNLIST}}'] = radhomebtn
    strs['{{RADHOMELIST}}'] = radhomelist
    strs['{{ROOTPATH}}'] = roothref
    strs['{{CSSINCLUDE}}'] = cssstr
    strs['{{JSINCLUDE}}'] = jsstr
    mkdir(os.path.join(config.html_out, 'rad'))
    # open the output file for writing
    with open(htmlpath, 'w') as hf:
        # need to open, replace, write several template files
        # top of page first
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'title.html'),
                   strs, hf)
        # nav bar
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'sidebar.html'),
                   strs, hf)
        # main page
        htmlc.write_html(os.path.join(config.html_in, 'rad', 'radhome.html'),
                   strs, hf)
        # footer
        htmlc.write_html(os.path.join(config.html_in, 'shared', 'footer.html'),
                   strs, hf)
