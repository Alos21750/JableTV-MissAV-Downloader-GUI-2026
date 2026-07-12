#!/usr/bin/env python
"""Generate .version files for PyInstaller --version-file."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from version_info import make_version

here = os.path.dirname(__file__)

v1 = make_version('JableTV_Modern', (2, 5, 26, 0),
                   'JableTV & MissAV Video Downloader GUI',
                   'JableTV_Modern.exe')
with open(os.path.join(here, 'JableTV_Modern.version'), 'w') as f:
    f.write(str(v1))

v2 = make_version('Jable_smalltool', (2, 5, 26, 0),
                   'JableTV & MissAV Batch Download Tool',
                   'Jable_smalltool.exe')
with open(os.path.join(here, 'Jable_smalltool.version'), 'w') as f:
    f.write(str(v2))

print('Generated version files.')
