# author: ALOS (Alos21750)
#!/usr/bin/env python
# coding: utf-8
"""English-language entry point for JableTV & MissAV Downloader."""

import ctypes
import sys

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from args import *
from gui_modern import gui_modern_main

save_folder = "download"

if __name__ == "__main__":
    url_arg = ""
    parser = get_parser()
    args = parser.parse_args()

    if len(args.url) != 0:
        url_arg = args.url
    elif args.random is True:
        url_arg = av_recommand()

    if args.nogui:
        M3U8Sites.consoles_main(url_arg, save_folder)
    else:
        gui_modern_main(url_arg, save_folder, lang='en')

    sys.exit(0)
