from solo.basic_files import mkdir
import os
import glob
import shutil

def get_rootpath(config, htmlpath):
    # return string rootpath based off of relative path
    itot = len(htmlpath.split('/'))
    ibase = len(config.html_out.split('/'))
    roothref = ''
    for i in range(itot-ibase-1):
        roothref = roothref + '../'
    return roothref

def write_html(htmlin, strs, htmlout):
    # find and replace strings in htmlin and write to htmlout
    with open(htmlin) as htmlf:
        for line in htmlf:
            for src, target in strs.items():
                line = line.replace(src, target)
            htmlout.write(line)

def copy_css_js(config):
    # copy all JS and CSS files from the input dirs to the output dirs
    cssfiles = glob.glob(os.path.join(config.css_in, '*'))
    jsfiles = glob.glob(os.path.join(config.js_in, '*'))
    mkdir(os.path.join(config.html_out, 'css'))
    mkdir(os.path.join(config.html_out, 'js'))
    for css in cssfiles:
        shutil.copy(css, os.path.join(config.html_out,'css'))
    for js in jsfiles:
        shutil.copy(js, os.path.join(config.html_out,'js'))
