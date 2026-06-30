# coding: utf-8
"""Global crash logging for the frozen GUI builds (issue #24).

A GUI app launched via pythonw has no console, so any uncaught exception just
makes the window vanish with no information. install() routes uncaught
exceptions (main thread + background threads) to a crash_log.txt next to the
exe and shows a copyable error dialog, so users can report what actually broke.
"""
import os
import sys
import threading
import traceback
from datetime import datetime


def _log_path():
    # next to the .exe when frozen, else next to this file
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    try:
        if not os.access(base, os.W_OK):
            raise OSError
    except Exception:
        base = os.path.expanduser("~")
    return os.path.join(base, "crash_log.txt")


def _app_version():
    try:
        import config
        return getattr(config, "APP_VERSION", "?")
    except Exception:
        return "?"


def _write(kind, exc_type, exc_value, exc_tb):
    try:
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        header = (
            "=" * 70 + "\n"
            + "JableTV crash log\n"
            + "time   : %s\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            + "version: %s\n" % _app_version()
            + "python : %s\n" % sys.version.split()[0]
            + "platform: %s\n" % sys.platform
            + "source : %s\n" % kind
            + "-" * 70 + "\n"
        )
        with open(_log_path(), "a", encoding="utf-8") as f:
            f.write(header + tb + "\n")
        return tb
    except Exception:
        return "".join(traceback.format_exception(exc_type, exc_value, exc_tb))


def _show_dialog(tb):
    path = _log_path()
    msg = (
        "JableTV 發生未預期的錯誤，已寫入記錄檔：\n%s\n\n"
        "請把這個檔案（或下面的訊息）貼到 GitHub issue，謝謝！\n"
        "An unexpected error occurred. A log was saved to:\n%s\n\n"
        "Please attach this file (or the text below) to a GitHub issue.\n\n"
        "%s"
    ) % (path, path, tb[-1500:])
    # Prefer a native Win32 MessageBox: it's process-global and safe even when a
    # Tk root already exists / its mainloop has died (building a 2nd tk.Tk() in a
    # crashing GUI app often double-faults). Fall back to a fresh Tk dialog only
    # if MessageBox is unavailable (non-Windows).
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "JableTV — Crash / 錯誤記錄", 0x10)
        return
    except Exception:
        pass
    try:
        import tkinter as tk
        from tkinter import scrolledtext
        win = tk.Tk()
        win.title("JableTV — Crash / 錯誤記錄")
        win.geometry("760x520")
        box = scrolledtext.ScrolledText(win, wrap="word")
        box.insert("1.0", msg)
        box.pack(fill="both", expand=True, padx=12, pady=8)
        tk.Button(win, text="關閉 Close", command=win.destroy).pack(pady=(0, 12))
        win.mainloop()
    except Exception:
        pass


def install(show_dialog=True):
    def hook(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        tb = _write("sys.excepthook", exc_type, exc_value, exc_tb)
        if show_dialog:
            _show_dialog(tb)

    sys.excepthook = hook

    # background threads (downloads/scrapers run on threads) — Python 3.8+
    try:
        def thook(args):
            if issubclass(args.exc_type, KeyboardInterrupt):
                return
            _write("threading[%s]" % getattr(args.thread, "name", "?"),
                   args.exc_type, args.exc_value, args.exc_traceback)
        threading.excepthook = thook
    except Exception:
        pass
