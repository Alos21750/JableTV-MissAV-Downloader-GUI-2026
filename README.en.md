<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Downloads-10_Parallel-00C853?style=for-the-badge" />
</p>

<h1 align="center">JableTV & MissAV Downloader — Material Design 2026</h1>
<p align="center"><strong>Jable TV Downloader ｜ MissAV Downloader ｜ Desktop GUI App</strong></p>
<p align="center"><strong>by ALOS</strong></p>

<p align="center">
  <a href="./README.md">繁體中文</a> ｜ English
</p>

> The best desktop tool for **Jable TV download** and **MissAV download**. Full GUI with built-in video browser, keyword search, multi-select batch download, and up to 10 parallel high-speed downloads. Portable Windows `.exe` — just double-click to run, no Python or installation needed. Supports FC2 videos, Chinese subtitle filtering, actress/category page bulk download, and M3U8/HLS streams.

---

## Screenshots (Native Material Design UI)

### JableTV Browse
<p align="center">
  <img src="./img/screenshot_browse_jable.png" width="800" alt="Jable TV download GUI — browse and select videos from JableTV" />
</p>

### MissAV Browse
<p align="center">
  <img src="./img/screenshot_browse_missav.png" width="800" alt="MissAV download GUI — browse and select videos from MissAV" />
</p>

### Download Manager (Live Progress Bars)
<p align="center">
  <img src="./img/screenshot_download.png" width="800" alt="Jable TV MissAV batch download manager with live progress bars" />
</p>

### Settings
<p align="center">
  <img src="./img/screenshot_settings.png" width="800" alt="JableTV MissAV Downloader settings — speed limit and concurrent downloads" />
</p>

---

## Two Tools

This project ships two independent executables:

| Tool | Purpose | Target user |
|------|---------|-------------|
| **JableTV_Modern.exe** | Full downloader — browse, search, multi-select, concurrent downloads | Anyone who wants to actively pick videos to download |
| **Jable_smalltool.exe** | Daily auto-downloader for `中文字幕` (Chinese-subtitled) releases — set the folder once and leave it running | Anyone who wants a set-and-forget feed of the newest subtitled releases |

## Features (JableTV_Modern.exe)

- **Native Material Design UI** — Built with CustomTkinter, dark theme, no browser required
- **Built-in Browser** — Browse video categories and search directly within the app, with full pagination
- **Multi-Select Download** — Check multiple videos in the browse panel, send to download queue in one click
- **Parallel Downloads (up to 10)** — Download up to 10 videos concurrently; configurable in Settings (default 2)
- **Speed Rate Limiting** — Configurable bandwidth limit (1/2/5/10/15 MB/s or unlimited)
- **Real-Time Progress** — Per-item progress, speed & status (incremental UI updates — no flicker)
- **Smart Clipboard** — Auto-detects video URLs copied to clipboard
- **Import from File** — Batch-import URLs from `.txt` / `.csv` files
- **Open Folder** — One-click to open the download destination folder
- **Auto Merge** — Automatically merges TS segments into a complete MP4 after download
- **Resume Support** — Cancelled downloads can be restarted; completed segments are preserved
- **High DPI Support** — Automatically adapts to high-resolution displays for crisp UI
- **Settings Tab** — Configure download speed, save location, and concurrency
- **Portable Windows Build** — Pre-packaged `.exe`, no Python installation needed

## Features (Jable_smalltool.exe)

- **Set once, runs daily** — Pick the save folder once and the tool checks for new videos every 24 hours
- **Focused on Chinese-subtitled** — Watches `jable.tv/tags/chinese-subtitle/` only
- **Deduped by memory** — Already-seen URLs are stored in `.Jable_smalltool/seen.json` so nothing downloads twice
- **First-run backfill** — Scans 3 pages the first time to catch the recent backlog; subsequent daily runs scan 2 pages
- **Check-now button** — Don't want to wait 24 h? Trigger an immediate scan
- **Background friendly** — Minimize to the taskbar and forget

## Supported Sites

| Site | Browse | Search | Download |
|------|:------:|:------:|:--------:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ai) | ✅ | ✅ | ✅ |
| Other M3U8 sites | — | — | ✅ |

## Quick Start

### 🖥️ Windows Users (Recommended)

Go to **[Releases](../../releases)** and download:

- **JableTV_Modern.exe** — Full downloader (~27 MB)
- **Jable_smalltool.exe** — Chinese-subtitle daily auto-downloader (~21 MB)

Double-click to run — **no Python installation needed**.

### 🐍 macOS / Linux / Other Platforms

```bash
# 1. Make sure Python 3.8+ is installed
python --version

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch the full downloader GUI
python main.py

# 4. Launch the Chinese-subtitle daily auto-downloader
python jable_smalltool.py

# 5. CLI mode (optional)
python main.py -nogui True
```

## Usage

1. **Browse Tab** — Pick a site & category, browse thumbnails with pagination, select videos, click "Download Selected"
2. **Download Tab** — Paste video URLs or import from file, click "Download All"
3. **Queue Management** — Active downloads show progress; pending items auto-start
4. **Settings Tab** — Configure speed limit, save location
5. **Open Folder** — Click the folder button to view downloaded videos
6. **Cancel / Cancel All** — Stop any or all downloads at any time

## Technical Details

- M3U8 stream protocol parsing & multi-threaded download
- AES-128 encrypted stream auto-decryption
- Automatic TS segment merging to MP4 (no FFmpeg required)
- Token-bucket rate limiter shared across all parallel downloads
- `ThreadPoolExecutor` for parallel download management
- Thread-safe Tkinter queue design for GUI updates
- Per-Monitor DPI V2 support for high-resolution displays

---

## Disclaimer

> **This tool is for educational and technical research purposes only.** Users must comply with local laws and respect content copyrights. The developer assumes no legal responsibility for any consequences arising from the use of this tool. Do not use this tool for any illegal or infringing purposes.

## Credits

Based on [hcjohn463/JableDownload](https://github.com/hcjohn463/JableDownload) and [AlfredoUen/JableTV](https://github.com/AlfredoUen/JableTV).

## Author

**ALOS** — [GitHub](https://github.com/Alos21750)

## Related Keywords

`Jable TV download` `JableTV downloader` `Jable video download` `MissAV download` `MissAV downloader` `Jable TV downloader GUI` `jable.tv batch download` `missav batch download` `M3U8 downloader` `HLS video download` `FC2 download` `Chinese subtitle download` `AV downloader` `video downloader GUI` `jable tv download tool` `missav download tool` `jable 下載` `missav 下載器`

## License

[Apache License 2.0](LICENSE)
