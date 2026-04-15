#!/usr/bin/env python
# coding: utf-8

import threading
import io
import tkinter as tk
import tkinter.ttk as ttk
import requests
from PIL import ImageTk, Image
from config import headers
from M3U8Sites.SiteJableTV import JableTVBrowser
from M3U8Sites.SiteMissAV import MissAVBrowser

# ── Design tokens (synced with gui.py) ───────────────────────────────────
BG        = '#0d0d18'
BG_CARD   = '#161630'
BG_CARD_HL= '#1e1e40'
BG_BAR    = '#101020'
BG_INPUT  = '#1c1c38'
ACCENT    = '#e94560'
ACCENT2   = '#7b61ff'
TEXT_PRI  = '#f0f0f8'
TEXT_SEC  = '#a0a0c0'
TEXT_DIM  = '#666688'
BORDER    = '#2a2a48'
DIVIDER   = '#222240'
SUCCESS   = '#4ade80'

THUMB_H   = 180     # 16:9 aspect ratio
MIN_CARD_W = 220    # minimum card width before reducing columns
CARD_PAD  = 8


def _truncate(text, n=68):
    return text if len(text) <= n else text[:n - 1] + '…'


# ── Thumbnail loader ─────────────────────────────────────────────────────
_thumb_session = None
_thumb_lock = threading.Lock()

def _get_thumb_session():
    global _thumb_session
    if _thumb_session is None:
        with _thumb_lock:
            if _thumb_session is None:
                _thumb_session = requests.Session()
                a = requests.adapters.HTTPAdapter(pool_connections=8,
                                                  pool_maxsize=32)
                _thumb_session.mount('http://', a)
                _thumb_session.mount('https://', a)
    return _thumb_session


# ── Video card ───────────────────────────────────────────────────────────
class VideoCard(tk.Frame):
    """A single video thumbnail card with selection support."""

    def __init__(self, master, data, card_w=300, on_click=None, on_dblclick=None, **kw):
        super().__init__(master, bg=BG_CARD, bd=0, highlightthickness=2,
                         highlightbackground=BORDER, cursor='hand2', **kw)
        self._data = data
        self._card_w = card_w
        self._selected = False
        self._photo = None
        self._on_click = on_click
        self._on_dblclick = on_dblclick
        self._build()

    def _build(self):
        thumb_h = max(120, int(self._card_w * 9 / 16))
        self._thumb_frame = tk.Frame(self, bg='#0a0a18', height=thumb_h)
        self._thumb_frame.pack(fill='x')
        self._thumb_frame.pack_propagate(False)

        self._thumb_lbl = tk.Label(self._thumb_frame, bg='#0a0a18',
                                   fg=TEXT_DIM, text='...', font=('', 11))
        self._thumb_lbl.pack(expand=True)

        # Duration badge
        dur = self._data.get('duration', '')
        if dur:
            self._dur_lbl = tk.Label(self._thumb_frame, text=dur,
                                     bg='#000000', fg='#ffffff',
                                     font=('Consolas', 8, 'bold'),
                                     padx=4, pady=1)
            self._dur_lbl.place(relx=1.0, rely=1.0, anchor='se', x=-4, y=-4)
        else:
            self._dur_lbl = None

        # Title
        self._title_lbl = tk.Label(
            self, text=_truncate(self._data.get('title', ''), 76),
            bg=BG_CARD, fg=TEXT_PRI, font=('Microsoft YaHei', 9),
            wraplength=max(180, self._card_w - 16), justify='left', anchor='nw',
            padx=6, pady=5)
        self._title_lbl.pack(fill='x')

        # Bind clicks to self and all visible children
        for w in (self, self._thumb_frame, self._thumb_lbl, self._title_lbl):
            w.bind('<Button-1>', self._click)
            w.bind('<Double-Button-1>', self._dblclick)
            w.bind('<Enter>', self._enter)
            w.bind('<Leave>', self._leave)

    def _click(self, _e):
        if self._on_click:
            self._on_click(self._data['url'], self)

    def _dblclick(self, _e):
        if self._on_dblclick:
            self._on_dblclick(self._data['url'])

    def _enter(self, _e):
        if not self._selected:
            self.configure(highlightbackground=ACCENT2, bg=BG_CARD_HL)
            self._title_lbl.configure(bg=BG_CARD_HL)
            self._thumb_frame.configure(bg='#0c0c20')

    def _leave(self, _e):
        if not self._selected:
            self.configure(highlightbackground=BORDER, bg=BG_CARD)
            self._title_lbl.configure(bg=BG_CARD)
            self._thumb_frame.configure(bg='#0a0a18')

    def set_selected(self, sel):
        self._selected = sel
        if sel:
            self.configure(highlightbackground=ACCENT, highlightthickness=3,
                           bg=BG_CARD_HL)
            self._title_lbl.configure(bg=BG_CARD_HL, fg=ACCENT)
        else:
            self.configure(highlightbackground=BORDER, highlightthickness=2,
                           bg=BG_CARD)
            self._title_lbl.configure(bg=BG_CARD, fg=TEXT_PRI)

    def set_thumbnail(self, photo):
        self._photo = photo
        self._thumb_lbl.configure(image=photo, text='')


# ── Browse Panel ─────────────────────────────────────────────────────────
class BrowsePanel(tk.Frame):
    """Browsing panel: site switch, categories, search, thumbnail grid,
    multi-select, pagination, and direct download trigger."""

    SITES = {
        'JableTV':  {'browser': JableTVBrowser},
        'MissAV':   {'browser': MissAVBrowser},
    }

    def __init__(self, master, on_add_url=None, on_download_urls=None, **kw):
        super().__init__(master, bg=BG, **kw)
        self._on_add_url = on_add_url
        self._on_download_urls = on_download_urls
        self._site_key = 'JableTV'
        self._categories = []
        self._page = 1
        self._has_next = True
        self._current_base_url = ''
        self._cards = []
        self._selected_urls = set()
        self._loading = False
        self._build_style()
        self._build_ui()
        self._start_cat_load()

    def _build_style(self):
        s = ttk.Style(self)
        s.configure('B.TCombobox', fieldbackground=BG_INPUT, background=BG_INPUT,
                     foreground=TEXT_PRI, selectbackground=ACCENT,
                     bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                     arrowcolor=TEXT_SEC)
        s.map('B.TCombobox', fieldbackground=[('readonly', BG_INPUT)])

    def _build_ui(self):
        # ── Top bar ──────────────────────────────────────────────
        top = tk.Frame(self, bg=BG_BAR, pady=7)
        top.pack(fill='x')

        # Site
        sf = tk.Frame(top, bg=BG_BAR)
        sf.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(sf, text='站點', bg=BG_BAR, fg=TEXT_SEC,
                 font=('', 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._site_var = tk.StringVar(value='JableTV')
        self._site_cb = ttk.Combobox(sf, textvariable=self._site_var,
                                     values=list(self.SITES.keys()),
                                     state='readonly', width=10,
                                     style='B.TCombobox')
        self._site_cb.pack(side=tk.LEFT)
        self._site_cb.bind('<<ComboboxSelected>>', self._on_site_change)

        tk.Frame(top, bg=BORDER, width=1).pack(side=tk.LEFT, fill='y',
                                                padx=10, pady=4)

        # Category
        cf = tk.Frame(top, bg=BG_BAR)
        cf.pack(side=tk.LEFT)
        tk.Label(cf, text='分類', bg=BG_BAR, fg=TEXT_SEC,
                 font=('', 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._cat_var = tk.StringVar(value='載入中...')
        self._cat_cb = ttk.Combobox(cf, textvariable=self._cat_var,
                                    state='readonly', width=14,
                                    style='B.TCombobox')
        self._cat_cb.pack(side=tk.LEFT)
        self._cat_cb.bind('<<ComboboxSelected>>', self._on_cat_change)

        tk.Frame(top, bg=BORDER, width=1).pack(side=tk.LEFT, fill='y',
                                                padx=10, pady=4)

        # Search
        qf = tk.Frame(top, bg=BG_BAR)
        qf.pack(side=tk.LEFT)
        tk.Label(qf, text='搜尋', bg=BG_BAR, fg=TEXT_SEC,
                 font=('', 9)).pack(side=tk.LEFT, padx=(0, 4))
        self._q_var = tk.StringVar()
        self._q_entry = tk.Entry(qf, textvariable=self._q_var,
                                 bg=BG_INPUT, fg=TEXT_PRI,
                                 insertbackground=TEXT_PRI, relief='flat',
                                 font=('', 10), width=22,
                                 highlightthickness=1,
                                 highlightbackground=BORDER,
                                 highlightcolor=ACCENT)
        self._q_entry.pack(side=tk.LEFT, ipady=3)
        self._q_entry.bind('<Return>', self._on_search)
        tk.Button(qf, text='搜尋', bg=ACCENT, fg='#fff',
                  activebackground='#c73350', activeforeground='#fff',
                  relief='flat', font=('', 9, 'bold'), padx=10, pady=3,
                  bd=0, command=self._on_search, cursor='hand2'
                  ).pack(side=tk.LEFT, padx=(4, 0))

        # Selection controls (right side)
        self._sel_badge = tk.Label(top, text='', bg=BG_BAR, fg=ACCENT,
                                   font=('', 9, 'bold'))
        self._sel_badge.pack(side=tk.RIGHT, padx=6)

        self._btn_dlsel = tk.Button(
            top, text='下載選中', bg=ACCENT, fg='#fff',
            activebackground='#c73350', activeforeground='#fff',
            relief='flat', font=('', 9, 'bold'), padx=12, pady=3, bd=0,
            command=self._download_selected, cursor='hand2',
            state=tk.DISABLED)
        self._btn_dlsel.pack(side=tk.RIGHT, padx=(0, 2))

        self._btn_addsel = tk.Button(
            top, text='加入清單', bg=BG_CARD, fg=TEXT_PRI,
            activebackground='#2a2a4a', activeforeground='#fff',
            relief='flat', font=('', 9), padx=10, pady=3, bd=0,
            command=self._add_selected, cursor='hand2',
            state=tk.DISABLED)
        self._btn_addsel.pack(side=tk.RIGHT, padx=(0, 4))

        # ── Divider ──────────────────────────────────────────────
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill='x')

        # ── Scrollable grid ──────────────────────────────────────
        grid_outer = tk.Frame(self, bg=BG)
        grid_outer.pack(fill='both', expand=True)

        self._canvas = tk.Canvas(grid_outer, bg=BG, highlightthickness=0, bd=0)
        self._vsb = ttk.Scrollbar(grid_outer, orient=tk.VERTICAL,
                                  command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vsb.set)
        self._vsb.pack(side=tk.RIGHT, fill='y')
        self._canvas.pack(side=tk.LEFT, fill='both', expand=True)

        self._grid = tk.Frame(self._canvas, bg=BG)
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._grid, anchor='nw')
        self._actual_cols = 4
        self._card_w = 300  # will be recalculated on resize
        for c in range(self._actual_cols):
            self._grid.columnconfigure(c, weight=1, uniform='card')
        self._grid.bind('<Configure>',
                        lambda _: self._canvas.configure(
                            scrollregion=self._canvas.bbox('all')))
        self._canvas.bind('<Configure>', self._on_canvas_resize)
        self._canvas.bind('<MouseWheel>', self._on_wheel)
        self._grid.bind('<MouseWheel>', self._on_wheel)

        # Status overlay
        self._status_var = tk.StringVar(value='正在載入...')
        self._status_lbl = tk.Label(self._grid, textvariable=self._status_var,
                                    bg=BG, fg=TEXT_SEC,
                                    font=('Microsoft YaHei', 14))
        self._status_lbl.grid(row=0, column=0, columnspan=self._actual_cols,
                              pady=140, sticky='')

        # ── Bottom nav ───────────────────────────────────────────
        tk.Frame(self, bg=DIVIDER, height=1).pack(fill='x')
        nav = tk.Frame(self, bg=BG_BAR, pady=10)
        nav.pack(fill='x')

        # Center container for pagination controls
        nav_center = tk.Frame(nav, bg=BG_BAR)
        nav_center.pack(side=tk.LEFT, expand=True)

        def _nav_btn(parent, txt, cmd, accent=False):
            bg = ACCENT if accent else BG_CARD
            fg = '#fff' if accent else TEXT_PRI
            abg = '#c73350' if accent else ACCENT
            return tk.Button(parent, text=txt, bg=bg, fg=fg,
                             activebackground=abg, activeforeground='#fff',
                             relief='flat', font=('Microsoft YaHei', 11, 'bold'),
                             padx=18, pady=6, bd=0, command=cmd,
                             cursor='hand2')

        self._btn_first = _nav_btn(nav_center, '  «  首頁  ', lambda: self._goto(1))
        self._btn_first.pack(side=tk.LEFT, padx=(0, 6))
        self._btn_prev = _nav_btn(nav_center, '  ‹  上一頁  ', lambda: self._goto(self._page - 1))
        self._btn_prev.pack(side=tk.LEFT, padx=6)
        self._page_lbl = tk.Label(nav_center, text='---', bg=BG_BAR, fg=TEXT_PRI,
                                  font=('Microsoft YaHei', 12, 'bold'), width=10,
                                  anchor='center')
        self._page_lbl.pack(side=tk.LEFT, padx=10)
        self._btn_next = _nav_btn(nav_center, '  下一頁  ›  ', lambda: self._goto(self._page + 1), accent=True)
        self._btn_next.pack(side=tk.LEFT, padx=6)

        self._load_indicator = tk.Label(nav, text='', bg=BG_BAR, fg=ACCENT,
                                        font=('Microsoft YaHei', 10))
        self._load_indicator.pack(side=tk.RIGHT, padx=12)

        self._update_nav()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _browser(self):
        return self.SITES[self._site_key]['browser']

    def _set_status(self, msg):
        for c in self._cards:
            c.destroy()
        self._cards.clear()
        self._status_var.set(msg)
        self._status_lbl.grid(row=0, column=0, columnspan=self._actual_cols,
                              pady=140, sticky='')

    def _bind_wheel_recursive(self, widget):
        """Bind mousewheel to widget and all descendants."""
        widget.bind('<MouseWheel>', self._on_wheel)
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    # ── Events ───────────────────────────────────────────────────────────

    def _on_site_change(self, _e):
        self._site_key = self._site_var.get()
        self._categories.clear()
        self._selected_urls.clear()
        self._update_sel()
        self._set_status('載入分類中...')
        self._start_cat_load()

    def _on_cat_change(self, _e=None):
        idx = self._cat_cb.current()
        if idx < 0 or idx >= len(self._categories):
            return
        cat = self._categories[idx]
        self._current_base_url = cat['url']
        self._page = 1
        self._has_next = True
        self._selected_urls.clear()
        self._update_sel()
        self._trigger_load()

    def _on_search(self, _e=None):
        q = self._q_var.get().strip()
        if not q:
            return
        if self._site_key == 'JableTV':
            self._current_base_url = f'https://jable.tv/search/?q={q}'
        else:
            self._current_base_url = f'https://missav.ai/dm265/cn/search?query={q}'
        self._page = 1
        self._has_next = True
        self._selected_urls.clear()
        self._update_sel()
        self._trigger_load()

    def _on_canvas_resize(self, e):
        self._canvas.itemconfig(self._canvas_win, width=e.width)
        # Recalculate columns: fit as many as possible with min width
        min_slot = MIN_CARD_W + CARD_PAD * 2 + 4
        new_cols = max(1, e.width // min_slot)
        # Compute actual card content width (minus pad and borders)
        self._card_w = max(MIN_CARD_W, (e.width // new_cols) - CARD_PAD * 2 - 4)
        if new_cols != self._actual_cols and self._cards:
            self._actual_cols = new_cols
            self._relayout_cards()

    def _on_wheel(self, e):
        self._canvas.yview_scroll(int(-1 * (e.delta / 120)), 'units')

    def _goto(self, page):
        if page < 1 or (not self._has_next and page > self._page):
            return
        self._page = page
        self._trigger_load()

    # ── Category loading ─────────────────────────────────────────────────

    def _start_cat_load(self):
        threading.Thread(target=self._load_cats_bg, daemon=True).start()

    def _load_cats_bg(self):
        cats = self._browser().fetch_categories()
        self._categories = cats
        names = [c['name'] for c in cats]
        if names:
            self.after(0, lambda: self._apply_cats(names))
        else:
            self.after(0, lambda: self._set_status('無法載入分類'))

    def _apply_cats(self, names):
        self._cat_cb.configure(values=names)
        self._cat_var.set(names[0])
        self._on_cat_change()

    # ── Page loading ─────────────────────────────────────────────────────

    def _build_page_url(self):
        if self._site_key == 'JableTV':
            base = self._current_base_url
            if '?' in base:
                # Search URL: ?q=xxx — uses from_videos for pagination
                return f'{base}&from_videos={self._page}'
            # Category URL — uses ?from=N
            base = base.rstrip('/')
            return f'{base}/?from={self._page}'
        return MissAVBrowser.page_url(self._current_base_url, self._page)

    def _trigger_load(self):
        if self._loading:
            return
        self._loading = True
        self._set_status('載入中...')
        self._load_indicator.configure(text='載入中...')
        self._update_nav()
        threading.Thread(target=self._fetch_bg, daemon=True).start()

    def _fetch_bg(self):
        url = self._build_page_url()
        try:
            videos = self._browser().fetch_page(url)
        except Exception:
            videos = []
        self.after(0, lambda: self._render(videos))

    def _render(self, videos):
        for c in self._cards:
            c.destroy()
        self._cards.clear()
        self._status_lbl.grid_forget()
        self._loading = False

        if not videos:
            self._has_next = False
            self._set_status('沒有找到影片')
            self._update_nav()
            self._load_indicator.configure(text='')
            return

        # If we got a full page of results, assume there's a next page
        self._has_next = len(videos) >= 12

        cols = self._actual_cols
        card_w = self._card_w
        for c in range(cols + 1):
            self._grid.columnconfigure(c, weight=1 if c < cols else 0,
                                       uniform='card' if c < cols else '')

        for i, v in enumerate(videos):
            row, col = divmod(i, cols)
            card = VideoCard(self._grid, v, card_w=card_w,
                             on_click=self._toggle_select,
                             on_dblclick=self._quick_add)
            card.grid(row=row, column=col, padx=CARD_PAD,
                      pady=CARD_PAD, sticky='new')
            self._cards.append(card)
            self._bind_wheel_recursive(card)

            thumb_url = v.get('thumbnail', '')
            if thumb_url:
                threading.Thread(target=self._load_thumb,
                                 args=(thumb_url, card, card_w),
                                 daemon=True).start()

        self._canvas.yview_moveto(0)
        self._update_nav()
        self._load_indicator.configure(text=f'{len(videos)} 部')

    def _load_thumb(self, url, card, target_w=300):
        try:
            r = _get_thumb_session().get(url, headers=headers, timeout=20)
            if r.status_code != 200:
                return
            img = Image.open(io.BytesIO(r.content))
            thumb_h = max(120, int(target_w * 9 / 16))
            img = img.convert('RGB').resize((target_w, thumb_h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            card.after(0, lambda: card.set_thumbnail(photo))
        except Exception:
            pass

    # ── Selection ────────────────────────────────────────────────────────

    def _toggle_select(self, url, card):
        if url in self._selected_urls:
            self._selected_urls.discard(url)
            card.set_selected(False)
        else:
            self._selected_urls.add(url)
            card.set_selected(True)
        self._update_sel()

    def _quick_add(self, url):
        if self._on_add_url:
            self._on_add_url(url)
        self._flash('已加入下載清單')

    def _add_selected(self):
        if self._on_add_url:
            for url in list(self._selected_urls):
                self._on_add_url(url)
        n = len(self._selected_urls)
        self._clear_selection()
        self._flash(f'已加入 {n} 部到清單')

    def _download_selected(self):
        if self._on_download_urls and self._selected_urls:
            urls = list(self._selected_urls)
            self._on_download_urls(urls)
            n = len(urls)
            self._clear_selection()
            self._flash(f'{n} 部開始下載')

    def _clear_selection(self):
        self._selected_urls.clear()
        for c in self._cards:
            c.set_selected(False)
        self._update_sel()

    def _update_sel(self):
        n = len(self._selected_urls)
        if n:
            self._sel_badge.configure(text=f'已選 {n} 部')
            self._btn_addsel.configure(state=tk.NORMAL)
            self._btn_dlsel.configure(state=tk.NORMAL)
        else:
            self._sel_badge.configure(text='')
            self._btn_addsel.configure(state=tk.DISABLED)
            self._btn_dlsel.configure(state=tk.DISABLED)

    def _relayout_cards(self):
        """Re-grid existing cards when column count changes."""
        cols = self._actual_cols
        for c in range(cols + 1):
            self._grid.columnconfigure(c, weight=1 if c < cols else 0,
                                       uniform='card' if c < cols else '')
        for i, card in enumerate(self._cards):
            row, col = divmod(i, cols)
            card.grid(row=row, column=col, padx=CARD_PAD,
                      pady=CARD_PAD, sticky='new')

    def _flash(self, msg):
        old = self._load_indicator.cget('text')
        self._load_indicator.configure(text=msg, fg=SUCCESS)
        self.after(2500, lambda: self._load_indicator.configure(
            text=old, fg=ACCENT))

    # ── Pagination ───────────────────────────────────────────────────────

    def _update_nav(self):
        p = self._page
        self._page_lbl.configure(text=f'第 {p} 頁')
        can_prev = p > 1
        can_next = self._has_next and not self._loading
        self._btn_first.configure(
            state=tk.NORMAL if can_prev else tk.DISABLED,
            fg=TEXT_PRI if can_prev else TEXT_DIM)
        self._btn_prev.configure(
            state=tk.NORMAL if can_prev else tk.DISABLED,
            fg=TEXT_PRI if can_prev else TEXT_DIM)
        self._btn_next.configure(
            state=tk.NORMAL if can_next else tk.DISABLED,
            bg=ACCENT if can_next else '#2a1a25',
            fg='#fff' if can_next else TEXT_DIM)
