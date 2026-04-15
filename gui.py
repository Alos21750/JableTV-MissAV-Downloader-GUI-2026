#!/usr/bin/env python
# coding: utf-8

import os
import sys
import threading
import time
import queue as _queue
import tkinter as tk
import tkinter.ttk as ttk
import tkinter.filedialog
from tkinter import simpledialog, messagebox
import re
import csv

from browser import BrowsePanel
import M3U8Sites

# ── Design tokens ────────────────────────────────────────────────────────
BG        = '#0d0d18'
BG_CARD   = '#161630'
BG_INPUT  = '#1c1c38'
BG_HEADER = '#101020'
BG_SECTION= '#131328'    # subtle section background
ACCENT    = '#e94560'
ACCENT2   = '#7b61ff'
TEXT_PRI  = '#f0f0f8'
TEXT_SEC  = '#a0a0c0'     # brighter for readability
TEXT_DIM  = '#666688'
BORDER    = '#2a2a48'
DIVIDER   = '#222240'     # thin separator lines
SUCCESS   = '#4ade80'
WARNING   = '#fbbf24'
ERROR_C   = '#f87171'

FONT      = ('Microsoft YaHei', 11)
FONT_SM   = ('Microsoft YaHei', 10)
FONT_MONO = ('Consolas', 10)
FONT_TITLE = ('Microsoft YaHei', 14, 'bold')
FONT_SEC_TITLE = ('Microsoft YaHei', 11, 'bold')

MAX_CONCURRENT = 10


def gui_main(url, dest):
    win = MainWindow(dest=dest, url=url)
    win.mainloop()
    win.cancel_all()


# ── Style setup ──────────────────────────────────────────────────────────
def _cfg_ttk(root):
    dpi_scale = root.winfo_fpixels('1i') / 96.0
    row_h = max(32, int(36 * dpi_scale))

    s = ttk.Style()
    s.theme_use('clam')
    s.configure('Dark.TNotebook', background=BG_HEADER, borderwidth=0)
    s.configure('Dark.TNotebook.Tab', background=BG_CARD, foreground=TEXT_SEC,
                font=('Microsoft YaHei', 10, 'bold'), padding=[26, 10],
                borderwidth=0)
    s.map('Dark.TNotebook.Tab',
          background=[('selected', BG), ('active', '#1e1e3a')],
          foreground=[('selected', ACCENT), ('active', TEXT_PRI)])
    s.configure('Q.Treeview', background=BG_CARD, foreground=TEXT_PRI,
                fieldbackground=BG_CARD, borderwidth=0, rowheight=row_h,
                font=FONT_SM)
    s.configure('Q.Treeview.Heading', background='#1a1a35',
                foreground=TEXT_SEC, font=('Microsoft YaHei', 9, 'bold'),
                borderwidth=0, relief='flat', padding=[8, 6])
    s.map('Q.Treeview', background=[('selected', '#2a2a55')],
          foreground=[('selected', '#ffffff')])
    s.configure('Vertical.TScrollbar', background=BG_CARD, troughcolor=BG,
                bordercolor=BG, arrowcolor=TEXT_DIM, relief='flat', borderwidth=0)
    s.map('Vertical.TScrollbar', background=[('active', ACCENT), ('pressed', ACCENT)])
    s.configure('P.Horizontal.TProgressbar', troughcolor='#1a1a2e',
                background=ACCENT, borderwidth=0, relief='flat')


# ── Helpers ──────────────────────────────────────────────────────────────
def _btn(parent, text, cmd, accent=False, danger=False, **kw):
    bg = ACCENT if accent else ('#3a1a20' if danger else BG_CARD)
    fg = '#fff' if accent else (ERROR_C if danger else TEXT_PRI)
    abg = '#c73350' if accent else ('#2a1215' if danger else '#2a2a4a')
    return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                     activebackground=abg, activeforeground='#fff',
                     relief='flat', bd=0, font=FONT_SM, cursor='hand2',
                     padx=14, pady=5, **kw)


def _entry(parent, var=None, **kw):
    defaults = dict(bg=BG_INPUT, fg=TEXT_PRI, insertbackground=TEXT_PRI,
                    relief='flat', font=FONT, highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=ACCENT)
    defaults.update(kw)
    return tk.Entry(parent, textvariable=var, **defaults)


# ── Thread-safe console ──────────────────────────────────────────────────
class ConsoleBox(tk.Text):
    """Console widget. Thread-safe: any thread may call write()/print()."""

    def __init__(self, master, **kw):
        defaults = dict(bg='#0a0a14', fg=TEXT_PRI, font=FONT_MONO,
                        relief='flat', state='disabled', wrap='word',
                        insertbackground=TEXT_PRI, selectbackground=ACCENT2,
                        highlightthickness=1, highlightbackground=BORDER)
        defaults.update(kw)
        super().__init__(master, **defaults)
        self._mq = _queue.Queue()
        self._old_stdout = sys.stdout
        self._old_stderr = sys.stderr
        sys.stdout = self
        if sys.stderr is None:
            sys.stderr = self
        self.tag_configure('ok',   foreground=SUCCESS)
        self.tag_configure('warn', foreground=WARNING)
        self.tag_configure('err',  foreground=ERROR_C)
        self.tag_configure('info', foreground=TEXT_PRI)
        self._poll()

    def write(self, msg):
        if msg:
            self._mq.put(str(msg))
        return len(msg) if msg else 0

    def flush(self):
        pass

    def _poll(self):
        batch = 0
        while batch < 60:
            try:
                msg = self._mq.get_nowait()
                self._insert(msg)
                batch += 1
            except _queue.Empty:
                break
        self.after(80, self._poll)

    def _insert(self, msg):
        self.configure(state='normal')
        if '\r' in msg:
            for i, part in enumerate(msg.split('\r')):
                if i > 0:
                    self.delete('end-1l linestart', 'end-1c')
                if part:
                    self._append(part)
        else:
            self._append(msg)
        self.configure(state='disabled')

    def _append(self, text):
        tag = ('ok' if any(k in text for k in ('完成', '✓', '成功')) else
               'warn' if any(k in text for k in ('警告', '重試', '等待')) else
               'err' if any(k in text for k in ('錯誤', '失敗', 'Error')) else
               'info')
        self.insert('end', text, tag)
        self.see('end')

    def clear(self):
        self.configure(state='normal')
        self.delete('1.0', 'end')
        self.configure(state='disabled')

    def destroy(self):
        if sys.stdout is self:
            sys.stdout = self._old_stdout
        if sys.stderr is self:
            sys.stderr = self._old_stderr
        super().destroy()


# ── Download Queue Treeview ──────────────────────────────────────────────
class DownloadQueue(ttk.Treeview):
    COLS = ('狀態', '名稱', '進度', '速度', '網址')
    STATUS_TAG = {
        '下載中': ACCENT, '準備中': ACCENT2, '等待中': WARNING,
        '已下載': SUCCESS, '未完成': WARNING, '已取消': TEXT_DIM,
        '網址錯誤': ERROR_C,
    }

    def __init__(self, master, **kw):
        frame = tk.Frame(master, bg=BG)
        super().__init__(frame, style='Q.Treeview',
                         columns=self.COLS, show='headings', **kw)
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.yview,
                           style='Vertical.TScrollbar')
        self.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill='y')
        self.pack(side=tk.LEFT, fill='both', expand=True)

        self.heading('狀態', text='狀態')
        self.heading('名稱', text='名稱')
        self.heading('進度', text='進度')
        self.heading('速度', text='速度')
        self.heading('網址', text='網址')
        self.column('狀態', width=72, stretch=False)
        self.column('名稱', stretch=True, minwidth=160)
        self.column('進度', width=72, stretch=False)
        self.column('速度', width=90, stretch=False)
        self.column('網址', width=200, stretch=False)

        for state, color in self.STATUS_TAG.items():
            self.tag_configure(state, foreground=color)

        self.bind('<Delete>', self._on_delete)
        self._frame = frame
        self.pack   = frame.pack
        self.grid   = frame.grid
        self.place  = frame.place
        self.modified = False

    def _iid(self, url):
        return str(hash(url))

    def _on_delete(self, _e):
        sel = self.selection()
        if not sel:
            return
        if not messagebox.askyesno('刪除', f'刪除選取的 {len(sel)} 個項目?'):
            return
        for iid in sel:
            self.delete(iid)
        self.modified = True

    def add_item(self, url, name='', state=''):
        iid = self._iid(url)
        if not self.exists(iid):
            self.insert('', 'end', iid=iid,
                        values=(state, name or url.rstrip('/').split('/')[-1],
                                '', '', url),
                        tags=(state,))
            self.modified = True
        elif name:
            old_name = self.set(iid, '名稱')
            if name != old_name and old_name == url.rstrip('/').split('/')[-1]:
                self.set(iid, '名稱', name)

    def set_state(self, url, state, progress='', speed='', name=''):
        iid = self._iid(url)
        if not self.exists(iid):
            return
        self.set(iid, '狀態', state)
        if progress:
            self.set(iid, '進度', progress)
        if speed:
            self.set(iid, '速度', speed)
        if name:
            self.set(iid, '名稱', name)
        self.item(iid, tags=(state,))
        self.modified = True

    def exists_url(self, url):
        return self.exists(self._iid(url))

    def all_urls(self):
        return [self.set(iid, '網址') for iid in self.get_children()]

    def save_csv(self, path):
        if not self.modified:
            return
        with open(path, 'w', encoding='utf-8', newline='') as f:
            w = csv.writer(f)
            w.writerow(self.COLS)
            for iid in self.get_children():
                w.writerow([self.set(iid, c) for c in self.COLS])
        self.modified = False

    def load_csv(self, path):
        if not os.path.exists(path):
            return
        with open(path, 'r', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                url = row.get('網址', '')
                if url:
                    self.add_item(url, row.get('名稱', ''), row.get('狀態', ''))
        self.modified = False


# ── Download Manager (10 parallel) ───────────────────────────────────────
class _DownloadManager:
    """Runs up to MAX_CONCURRENT downloads. Excess items are queued."""

    def __init__(self, widget, on_state, on_progress):
        self._widget = widget          # for .after() scheduling
        self._on_state = on_state      # (url, state, **kw)
        self._on_progress = on_progress  # (url, done, total, speed)
        self._pending = []             # [(url, dest), ...]
        self._active = {}              # url -> job
        self._lock = threading.Lock()

    @property
    def active_count(self):
        with self._lock:
            return len(self._active)

    @property
    def pending_count(self):
        with self._lock:
            return len(self._pending)

    def enqueue(self, url, dest):
        with self._lock:
            if url in self._active:
                return
            if any(u == url for u, _ in self._pending):
                return
            if len(self._active) < MAX_CONCURRENT:
                self._active[url] = None  # placeholder
                threading.Thread(target=self._run, args=(url, dest),
                                 daemon=True).start()
            else:
                self._pending.append((url, dest))
                self._safe_state(url, '等待中')

    def cancel(self, url):
        with self._lock:
            self._pending = [(u, d) for u, d in self._pending if u != url]
            job = self._active.pop(url, None)
        if job:
            threading.Thread(target=job.cancel_download, daemon=True).start()
            self._safe_state(url, '已取消')

    def cancel_all(self):
        with self._lock:
            for u, _ in self._pending:
                self._safe_state(u, '已取消')
            self._pending.clear()
            jobs = list(self._active.items())
        for url, job in jobs:
            if job:
                try:
                    job.cancel_download()
                except Exception:
                    pass
            self._safe_state(url, '已取消')
        with self._lock:
            self._active.clear()

    def _run(self, url, dest):
        self._safe_state(url, '準備中')
        try:
            job = M3U8Sites.CreateSite(url, dest)
            if not job or not job.is_url_vaildate():
                with self._lock:
                    self._active.pop(url, None)
                self._safe_state(url, '網址錯誤')
                self._try_next()
                return
            with self._lock:
                self._active[url] = job
            name = job.target_name() or ''
            self._safe_state(url, '下載中', name=name)
            job._progress_callback = lambda d, t, s: self._handle_progress(url, d, t, s)
            job.start_download()
            with self._lock:
                self._active.pop(url, None)
            if job._cancel_job:
                self._safe_state(url, '已取消')
            else:
                self._safe_state(url, '已下載', progress='100%', speed='')
        except Exception:
            with self._lock:
                self._active.pop(url, None)
            self._safe_state(url, '未完成')
        self._try_next()

    def _try_next(self):
        with self._lock:
            if not self._pending or len(self._active) >= MAX_CONCURRENT:
                return
            url, dest = self._pending.pop(0)
            self._active[url] = None
        threading.Thread(target=self._run, args=(url, dest), daemon=True).start()

    def _safe_state(self, url, state, **kw):
        self._widget.after(0, lambda: self._on_state(url, state, **kw))

    def _handle_progress(self, url, done, total, speed_bps):
        if total <= 0:
            return
        pct = int(done * 100 / total)
        spd = (f'{speed_bps / 1024:.0f} KB/s' if speed_bps < 1024 * 1024
               else f'{speed_bps / 1024 / 1024:.1f} MB/s')
        self._widget.after(0, lambda: self._on_progress(url, pct, spd))


# ── Main window ──────────────────────────────────────────────────────────
class MainWindow(tk.Tk):
    CSV_PATH = os.path.join(os.getcwd(), 'JableTV.csv')

    def __init__(self, dest='download', url=''):
        super().__init__()
        self.title('JableTV & MissAV Downloader')
        self.minsize(980, 660)
        self.configure(bg=BG)
        # Start maximized; geometry is fallback if zoomed fails
        try:
            self.state('zoomed')
        except tk.TclError:
            self.geometry('1340x880')
        _cfg_ttk(self)

        self._dest = dest
        self._url = url
        self._is_closing = False
        self._clp_text = ''

        self._dlmgr = _DownloadManager(
            self, self._on_dl_state, self._on_dl_progress)

        self._build_ui()
        self._queue_tree.load_csv(self.CSV_PATH)

        self.protocol('WM_DELETE_WINDOW', self._on_close)
        threading.Thread(target=self._clipboard_monitor, daemon=True).start()

        if url:
            self._url_var.set(url)

    # ── Build UI ─────────────────────────────────────────────────────────

    def _build_ui(self):
        nb = ttk.Notebook(self, style='Dark.TNotebook')
        nb.pack(fill='both', expand=True)
        self._notebook = nb

        # Tab 1: Browse
        browse_frame = tk.Frame(nb, bg=BG)
        nb.add(browse_frame, text='  瀏覽  ')
        self._browse = BrowsePanel(browse_frame,
                                   on_add_url=self._from_browser,
                                   on_download_urls=self._download_from_browser)
        self._browse.pack(fill='both', expand=True)

        # Tab 2: Downloads
        dl_frame = tk.Frame(nb, bg=BG)
        nb.add(dl_frame, text='  下載  ')
        self._build_dl_tab(dl_frame)

    def _build_dl_tab(self, parent):
        # ── Input section ─────────────────────────────────────────
        input_section = tk.Frame(parent, bg=BG_SECTION, padx=16, pady=12)
        input_section.pack(fill='x')

        r1 = tk.Frame(input_section, bg=BG_SECTION)
        r1.pack(fill='x', pady=(0, 6))
        tk.Label(r1, text='存放位置', bg=BG_SECTION, fg=TEXT_SEC,
                 font=FONT_SM, width=8, anchor='e').pack(side=tk.LEFT)
        self._dest_var = tk.StringVar(value=self._dest)
        _entry(r1, var=self._dest_var, width=70).pack(
            side=tk.LEFT, fill='x', expand=True, padx=(8, 0), ipady=5)
        _btn(r1, '瀏覽...', self._pick_dest).pack(side=tk.LEFT, padx=(8, 0))

        r2 = tk.Frame(input_section, bg=BG_SECTION)
        r2.pack(fill='x')
        tk.Label(r2, text='下載網址', bg=BG_SECTION, fg=TEXT_SEC,
                 font=FONT_SM, width=8, anchor='e').pack(side=tk.LEFT)
        self._url_var = tk.StringVar()
        _entry(r2, var=self._url_var, width=70).pack(
            side=tk.LEFT, fill='x', expand=True, padx=(8, 0), ipady=5)

        # ── Action bar ────────────────────────────────────────────
        tk.Frame(parent, bg=DIVIDER, height=1).pack(fill='x')
        bar = tk.Frame(parent, bg=BG_HEADER, pady=8, padx=14)
        bar.pack(fill='x')

        # Primary actions (left)
        _btn(bar, '▶  下載', self._start_one, accent=True).pack(
            side=tk.LEFT, padx=(0, 6))
        _btn(bar, '▶▶ 全部下載', self._start_all, accent=True).pack(
            side=tk.LEFT, padx=(0, 6))

        # Separator
        tk.Frame(bar, bg=DIVIDER, width=1).pack(
            side=tk.LEFT, fill='y', padx=10, pady=2)

        # Secondary actions
        _btn(bar, '加入清單', self._add_to_list).pack(side=tk.LEFT, padx=4)
        _btn(bar, '導入文件', self._import_file).pack(side=tk.LEFT, padx=4)

        # Right side
        _btn(bar, '全部取消', self._cancel_all_cmd, danger=True).pack(
            side=tk.RIGHT, padx=(6, 0))
        _btn(bar, '清除訊息', self._clear_console).pack(
            side=tk.RIGHT, padx=4)
        _btn(bar, '📂 開啟資料夾', self._open_dest_folder).pack(
            side=tk.RIGHT, padx=4)

        # ── Status bar ────────────────────────────────────────────
        tk.Frame(parent, bg=DIVIDER, height=1).pack(fill='x')
        status_bar = tk.Frame(parent, bg=BG_HEADER, pady=6, padx=16)
        status_bar.pack(fill='x')
        self._status_lbl = tk.Label(status_bar, text='就緒', bg=BG_HEADER,
                                    fg=TEXT_SEC, font=('Consolas', 10),
                                    anchor='w')
        self._status_lbl.pack(fill='x')
        tk.Frame(parent, bg=DIVIDER, height=1).pack(fill='x')

        # ── Queue treeview ────────────────────────────────────────
        self._queue_tree = DownloadQueue(parent)
        self._queue_tree.pack(fill='both', expand=True, padx=0, pady=0)

        # ── Console section ───────────────────────────────────────
        tk.Frame(parent, bg=DIVIDER, height=1).pack(fill='x')
        console_header = tk.Frame(parent, bg=BG_HEADER, padx=16, pady=4)
        console_header.pack(fill='x')
        tk.Label(console_header, text='輸出訊息', bg=BG_HEADER,
                 fg=TEXT_DIM, font=('Microsoft YaHei', 8)).pack(
            side=tk.LEFT)

        console_frame = tk.Frame(parent, bg=BG)
        console_frame.pack(fill='x', padx=0, pady=(0, 0))
        self._console = ConsoleBox(console_frame, height=4)
        csb = ttk.Scrollbar(console_frame, orient=tk.VERTICAL,
                            command=self._console.yview,
                            style='Vertical.TScrollbar')
        self._console.configure(yscrollcommand=csb.set)
        csb.pack(side=tk.RIGHT, fill='y')
        self._console.pack(fill='both', expand=True)

        self._update_status()

    # ── Browse → Download bridges ────────────────────────────────────────

    def _from_browser(self, url):
        """Single video added from browse (double-click)."""
        self._add_url(url)
        self._notebook.select(1)

    def _download_from_browser(self, urls):
        """Multi-select download from browse page."""
        dest = self._dest_var.get() or 'download'
        for url in urls:
            if M3U8Sites.VaildateUrl(url):
                self._queue_tree.add_item(url, state='等待中')
                self._dlmgr.enqueue(url, dest)
        self._update_status()

    # ── Download helpers ─────────────────────────────────────────────────

    def _pick_dest(self):
        d = tkinter.filedialog.askdirectory()
        if d:
            self._dest_var.set(d)

    def _open_dest_folder(self):
        import subprocess, platform
        dest = self._dest_var.get() or 'download'
        folder = os.path.abspath(dest)
        if not os.path.isdir(folder):
            os.makedirs(folder, exist_ok=True)
        system = platform.system()
        if system == 'Windows':
            os.startfile(folder)
        elif system == 'Darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])

    def _add_url(self, url, show_msg=True):
        if not M3U8Sites.VaildateUrl(url):
            if show_msg:
                print(f'不支援的網址: {url}')
            return False
        if self._queue_tree.exists_url(url):
            if show_msg:
                print(f'已在清單中: {url}')
            return False
        self._queue_tree.add_item(url)
        return True

    def _add_to_list(self):
        url = self._url_var.get().strip()
        if not url:
            print('請先輸入網址')
            return
        if M3U8Sites.VaildateUrl(url):
            self._add_url(url)
        else:
            jlist = M3U8Sites.CreateSiteUrlList(url)
            if jlist and jlist.isVaildLinks():
                _VideoListDlg(self, jlist)
            else:
                print(f'不支援的網址: {url}')

    def _start_one(self):
        url = self._url_var.get().strip()
        dest = self._dest_var.get() or 'download'
        if not url:
            print('請先輸入網址')
            return
        if not M3U8Sites.VaildateUrl(url):
            print(f'不支援的網址: {url}')
            return
        self._queue_tree.add_item(url, state='等待中')
        self._dlmgr.enqueue(url, dest)
        self._update_status()

    def _start_all(self):
        dest = self._dest_var.get() or 'download'
        children = self._queue_tree.get_children()
        if not children:
            print('下載清單是空的，請先加入網址')
            return
        count = 0
        for iid in children:
            state = self._queue_tree.set(iid, '狀態')
            if state in ('已下載', '下載中', '準備中', '等待中'):
                continue
            url = self._queue_tree.set(iid, '網址')
            self._queue_tree.set_state(url, '等待中')
            self._dlmgr.enqueue(url, dest)
            count += 1
        if count == 0:
            print('清單中沒有需要下載的項目')
        else:
            print(f'已加入 {count} 個下載任務')
        self._update_status()

    def _cancel_all_cmd(self):
        self._dlmgr.cancel_all()
        self._update_status()

    def cancel_all(self):
        self._is_closing = True
        self._dlmgr.cancel_all()

    # ── Download callbacks (called on main thread via .after) ────────────

    def _on_dl_state(self, url, state, name='', progress='', speed=''):
        self._queue_tree.set_state(url, state, progress=progress,
                                   speed=speed, name=name)
        self._update_status()

    def _on_dl_progress(self, url, pct, speed_str):
        self._queue_tree.set_state(url, '下載中',
                                   progress=f'{pct}%', speed=speed_str)

    def _update_status(self):
        a = self._dlmgr.active_count
        p = self._dlmgr.pending_count
        parts = []
        if a:
            parts.append(f'下載中 {a}/{MAX_CONCURRENT}')
        if p:
            parts.append(f'等待中 {p}')
        done = sum(1 for iid in self._queue_tree.get_children()
                   if self._queue_tree.set(iid, '狀態') == '已下載')
        if done:
            parts.append(f'已完成 {done}')
        self._status_lbl.configure(text='  |  '.join(parts) if parts else '就緒')

    # ── Import file ──────────────────────────────────────────────────────

    def _import_file(self):
        fname = tkinter.filedialog.askopenfilename(
            filetypes=[('文字檔', '*.txt *.csv'), ('全部', '*.*')])
        if not fname:
            return
        count = 0
        with open(fname, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                for m in re.finditer(r'https?://\S+', line):
                    url = m.group(0).rstrip('.,;)\'"')
                    if self._add_url(url, show_msg=False):
                        count += 1
        print(f'已載入 {count} 個網址')

    # ── Clipboard monitor ────────────────────────────────────────────────

    def _clipboard_monitor(self):
        while not self._is_closing:
            try:
                clp = self.clipboard_get()
                if clp != self._clp_text:
                    self._clp_text = clp
                    for m in re.finditer(r'https?://\S+', clp):
                        url = m.group(0).rstrip('.,;)\'"')
                        if M3U8Sites.VaildateUrl(url) and \
                                not self._queue_tree.exists_url(url):
                            self.after(0, lambda u=url: self._add_url(u, False))
            except Exception:
                pass
            time.sleep(0.8)

    # ── Console ──────────────────────────────────────────────────────────

    def _clear_console(self):
        self._console.clear()

    # ── Close ────────────────────────────────────────────────────────────

    def _on_close(self):
        self._is_closing = True
        self.cancel_all()
        self._queue_tree.save_csv(self.CSV_PATH)
        self.destroy()


# ── Video list dialog ────────────────────────────────────────────────────
class _VideoListDlg(tk.Toplevel):

    def __init__(self, master, jlist):
        super().__init__(master)
        self._jlist = jlist
        self._master = master
        self.grab_set()
        self.configure(bg=BG)
        self.title(f'[{jlist.getListType()}]  {jlist.getTotalPages()} 頁'
                   f' / {jlist.getTotalLinks()} 部')
        self.geometry('780x520')
        self._sortby = jlist.getSortType()
        self._build()
        self._load_page(jlist.getCurrentPage())

    def _build(self):
        self._listbox = tk.Listbox(
            self, bg=BG_CARD, fg=TEXT_PRI, selectmode=tk.EXTENDED,
            font=FONT_SM, relief='flat', selectbackground=ACCENT,
            activestyle='none', highlightthickness=0, bd=0)
        self._listbox.pack(fill='both', expand=True, padx=8, pady=8)

        ctrl = tk.Frame(self, bg=BG, pady=6)
        ctrl.pack(fill='x', padx=8)
        _btn(ctrl, '« 首頁', lambda: self._load_page(0)).pack(
            side=tk.LEFT, padx=2)
        _btn(ctrl, '上一頁', self._prev).pack(side=tk.LEFT, padx=2)
        self._lbl = tk.Label(ctrl, text='1', bg=BG, fg=TEXT_PRI,
                             font=FONT_MONO, width=10)
        self._lbl.pack(side=tk.LEFT)
        _btn(ctrl, '下一頁', self._next).pack(side=tk.LEFT, padx=2)
        _btn(ctrl, '末頁 »',
             lambda: self._load_page(self._jlist.getTotalPages() - 1)).pack(
            side=tk.LEFT, padx=2)

        if self._sortby is not None:
            self._sort_var = tk.StringVar(value=self._sortby)
            cb = ttk.Combobox(ctrl, textvariable=self._sort_var,
                              values=self._jlist.getSortTypeList(),
                              state='readonly', width=12)
            cb.pack(side=tk.LEFT, padx=8)
            cb.bind('<<ComboboxSelected>>', self._sort_changed)

        _btn(ctrl, '加入清單', self._commit, accent=True).pack(
            side=tk.RIGHT, padx=2)
        _btn(ctrl, '關閉', self.destroy).pack(side=tk.RIGHT, padx=2)

    def _load_page(self, idx):
        self._jlist.loadPageAtIndex(idx, self._sortby)
        self._listbox.delete(0, tk.END)
        for desc in self._jlist.getLinkDescs():
            self._listbox.insert(tk.END, desc)
        self._lbl.configure(text=f'{idx + 1}')

    def _prev(self):
        self._load_page(max(0, self._jlist.getCurrentPage() - 1))

    def _next(self):
        self._load_page(min(self._jlist.getTotalPages() - 1,
                            self._jlist.getCurrentPage() + 1))

    def _sort_changed(self, _e):
        self._sortby = self._sort_var.get()
        self._load_page(self._jlist.getCurrentPage())

    def _commit(self):
        links = self._jlist.getLinks()
        for i in self._listbox.curselection():
            if i < len(links):
                self._master._add_url(links[i], show_msg=False)
        self.destroy()
