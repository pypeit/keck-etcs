# Standard imports
import glob, os
from setuptools import setup, find_packages


# Begin setup
setup_keywords = dict()
setup_keywords['name'] = 'keck_etcs'
setup_keywords['description'] = 'Exposure time calculators for the Keck spectrographs, grounded in PypeIt data'
setup_keywords['author'] = 'J. Xavier Prochaska'
setup_keywords['author_email'] = 'jxp@ucsc.edu'
setup_keywords['license'] = 'BSD'
setup_keywords['url'] = 'https://github.com/pypeit/keck-etcs'
setup_keywords['version'] = '0.0.dev0'
# Use README.md as long_description.
setup_keywords['long_description'] = ''
if os.path.exists('README.md'):
    with open('README.md') as readme:
        setup_keywords['long_description'] = readme.read()
setup_keywords['provides'] = [setup_keywords['name']]
setup_keywords['python_requires'] = '>=3.11'
setup_keywords['install_requires'] = [
    'numpy', 'scipy', 'matplotlib', 'astropy',
    'IPython', 'pytest',
    # Source of throughputs, sky, extinction and detector parameters;
    # see requirements.txt on installing the local checkout
    'pypeit']
setup_keywords['zip_safe'] = False
setup_keywords['packages'] = find_packages()

if os.path.isdir('bin'):
    setup_keywords['scripts'] = [fname for fname in glob.glob(os.path.join('bin', '*'))
                                 if not os.path.basename(fname).endswith('.rst')]

setup(**setup_keywords)
