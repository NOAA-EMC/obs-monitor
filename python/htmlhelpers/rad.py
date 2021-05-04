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

def proc_figlist_btnimg(htmlstr, figlist, figrelpath, type=''):
    # loop through radiance figures and return modified HTML
    for ifig in figlist:
        ifig_name = ''.join(os.path.basename(ifig).split('_')[2:-1])
        ifig_name = ifig_name.replace('brightness temperature', 'channel')
        link = figrelpath + os.path.basename(ifig) # replace later with correct URL for args
        imgsrc = figrelpath + os.path.basename(ifig)
        htmlstr = htmlstr + f'<div class="btnimg filterDiv {type}"><a href="{link}"class="w3-bar-item w3-button w3-padding">{ifig_name}<img src="{imgsrc}"></a></div>\n'
    return htmlstr

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
    proc_figlist_btnimg(imgstr, scatterfigs, figrelpath, type='scatter')
    # non timeseries line plots
    btnstr = btnstr + f'<button class="btn w3-white" onclick="filterSelection(\'lineplt\')">Line</button>'
    linefigs = glob.glob(os.path.join(cycledir, rad['name'], '*_line.png'))
    # TODO sort by channel, maybe easier to save figure with leading zeros?
    proc_figlist_btnimg(imgstr, linefigs, figrelpath, type='lineplt')
    return btnstr, imgstr

def get_includes_rad(roothref):
    # return strings of includes for CSS style and javascript
    cssstr = f'<link rel="stylesheet" href="{roothref}css/rad.css">'
    jsstr = f'<script type="text/javascript" src="{roothref}js/rad.js"></script>'
    return cssstr, jsstr

def gen_sensor_view_menu(rad, config):
    # return HTML strings for the list of cycles, channels, and plots
    # for the specified sensor
    cychtml = ''
    chhtml = ''
    figshtml = ''
    # get list of cycles
    cycledirs = sorted(glob.glob(os.path.join(config.root_fig, '20*')))
    cycles = [os.path.basename(cycle) for cycle in cycledirs]
    for cycle in cycles:
        cyclelink = '#' # TODO fix this with javascript
        cychtml = cychtml + f'<a href="{cyclelink}">{cycle}</a>\n'
    # get list of channels
    matchfile = '*_*_hofx_scatter.png'
    pngfiles = sorted(glob.glob(os.path.join(config.root_fig,
                                             cycles[-1],
                                             rad['name'],
                                             matchfile)))
    chlist0 = [os.path.basename(p).split('_')[-3] for p in pngfiles]
    chlist = []
    for ch in chlist0:
        try:
            chlist.append(int(ch))
        except:
            chlist.append(0)
    chlist = sorted(chlist)
    for ch in chlist:
        chlink = '#' # TODO fix this with javacript
        chstr = 'all' if ch == 0 else str(ch)
        chhtml = chhtml + f'<a href="{chlink}">{chstr}</a>\n'
    # get list of figures
    figlist = []
    matchfile = '*_1_*.png'
    allfigs = glob.glob(os.path.join(config.root_fig,
                                     cycles[-1],
                                     rad['name'],
                                     matchfile))
    figlist0 = [os.path.basename(p).split('_')[-2:] for p in allfigs]
    figlist1 = [p[0]+'_'+p[1].split('.')[0] for p in figlist0]
    for png in figlist1:
        if png not in figlist:
            figlist.append(png)
    for png in figlist:
        figlink = '#' # TODO fix this with javascript
        pngname = png.replace('_',' ')
        figshtml = figshtml + f'<a href="{figlink}">{pngname}</a>\n'
    return cychtml, chhtml, figshtml

def gen_sensor_view(rad, config):
    # generate landing page for each sensor/platform combination
    # output html path
    htmldir = os.path.join(config.html_out, 'rad', rad['name'])
    mkdir(htmldir)
    htmlpath = os.path.join(htmldir, 'view.html')
    # get HTML of dropdown menus
    sensorcyc, sensorch, sensorfigs = gen_sensor_view_menu(rad, config)
    # get relative path for links
    roothref = htmlc.get_rootpath(config, htmlpath)
    # get includes of CSS and javascript
    cssstr, jsstr = get_includes_rad(roothref)
    strs = {}
    strs['{{PAGETITLE}}'] = rad['fullname']
    strs['{{CYCLEMENU}}'] = sensorcyc
    strs['{{CHANNELMENU}}'] = sensorch
    strs['{{PLOTMENU}}'] = sensorfigs
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
