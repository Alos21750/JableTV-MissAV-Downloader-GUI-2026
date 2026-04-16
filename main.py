# author: ALOS (Alos21750)
#!/usr/bin/env python
# coding: utf-8

import ctypes
import sys

# Enable DPI awareness BEFORE any Tk/GUI imports
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)   # Per-monitor V2
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from args import *

# Use modern NiceGUI by default; fall back to tkinter if unavailable
try:
    from gui_modern import gui_modern_main as _gui_main
    _USE_MODERN = True
except ImportError:
    from gui import gui_main as _gui_main
    _USE_MODERN = False

''' Default folder to save the download files
    "" or None : same as the url's last stem,  ie:  "abc-001" for url = "https://jable.tv/videos/abc-001/"
    others : relative to the current folder, or an absolute path  
    '''
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
    elif _USE_MODERN:
        _gui_main(url_arg, save_folder)
    else:
        from gui import gui_main
        gui_main(url_arg, save_folder)

    sys.exit(0)