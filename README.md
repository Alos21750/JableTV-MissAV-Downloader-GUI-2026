<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge" />
  <img src="https://img.shields.io/badge/GUI-Tkinter-FF6F00?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Downloads-10_Parallel-00C853?style=for-the-badge" />
</p>

<h1 align="center">JableTV & MissAV Downloader GUI 2026</h1>

<p align="center">
  <strong>🎬 高速串流影片下載器 ｜ High-Speed Streaming Video Downloader</strong>
</p>

<p align="center">
  <em>一鍵瀏覽、多選、批量下載 M3U8 串流影片，支援 10 路並行下載</em><br/>
  <em>Browse, multi-select & batch download M3U8 streaming videos with 10 parallel workers</em>
</p>

---

## Screenshots

### Browse — JableTV
<p align="center">
  <img src="./img/screenshot_browse_jable.png" width="800" alt="JableTV Browse" />
</p>

### Browse — MissAV
<p align="center">
  <img src="./img/screenshot_browse_missav.png" width="800" alt="MissAV Browse" />
</p>

### Download Manager
<p align="center">
  <img src="./img/screenshot_download.png" width="800" alt="Download Manager" />
</p>

---

## 繁體中文

### 功能特色

- **內建瀏覽器** — 直接在應用程式內瀏覽影片分類、搜尋關鍵字
- **多選下載** — 在瀏覽頁面勾選多部影片，一鍵送入下載佇列
- **10 路並行下載** — 同時下載最多 10 部影片，超出自動排隊等候
- **即時進度顯示** — 每部影片獨立顯示下載進度、速度、狀態
- **智慧剪貼簿** — 複製影片網址自動偵測並加入佇列
- **匯入文字檔** — 從 `.txt` / `.csv` 批量匯入網址
- **斷點續傳** — 取消後可重新下載，已完成的片段不會重複下載
- **Windows 免安裝** — 提供打包好的 `.exe` 執行檔，不需安裝 Python

### 支援網站

| 網站 | 瀏覽 | 搜尋 | 下載 |
|------|:----:|:----:|:----:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ws) | ✅ | ✅ | ✅ |
| 其他 M3U8 網站 | — | — | ✅ |

### 快速開始

#### 方法一：直接下載執行檔（推薦）

前往 [Releases](../../releases) 頁面下載最新版 `windowsGUI.exe`，雙擊即可執行。

#### 方法二：從原始碼執行

```bash
# 安裝相依套件
pip install -r requirements.txt

# 啟動圖形介面
python main.py

# 命令列模式
python main.py -nogui True
```

### 使用說明

1. **下載分頁** — 貼上影片網址或從檔案匯入，點擊「全部下載」
2. **瀏覽分頁** — 選擇網站與分類，瀏覽影片縮圖，勾選後點擊「下載所選」
3. **佇列管理** — 下載中的項目會顯示進度；等候中的項目排隊自動執行
4. **取消 / 全部取消** — 可隨時中止下載任務

### 技術細節

- 使用 M3U8 串流協定解析與下載
- FFmpeg 合併 TS 片段為 MP4
- `ThreadPoolExecutor` 管理並行下載
- Tkinter 主執行緒安全佇列設計

---

## English

### Features

- **Built-in Browser** — Browse video categories and search directly within the app
- **Multi-Select Download** — Check multiple videos in the browse panel, send to download queue in one click
- **10 Parallel Downloads** — Download up to 10 videos simultaneously; extras auto-queue
- **Real-Time Progress** — Individual progress bars, speed & status for each download
- **Smart Clipboard** — Auto-detects video URLs copied to clipboard
- **Import from File** — Batch-import URLs from `.txt` / `.csv` files
- **Resume Support** — Cancelled downloads can be restarted; completed segments are preserved
- **Portable Windows Build** — Pre-packaged `.exe`, no Python installation needed

### Supported Sites

| Site | Browse | Search | Download |
|------|:------:|:------:|:--------:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ws) | ✅ | ✅ | ✅ |
| Other M3U8 sites | — | — | ✅ |

### Quick Start

#### Option 1: Download the Executable (Recommended)

Go to [Releases](../../releases) and download the latest `windowsGUI.exe`. Double-click to run.

#### Option 2: Run from Source

```bash
# Install dependencies
pip install -r requirements.txt

# Launch GUI
python main.py

# CLI mode
python main.py -nogui True
```

### Usage

1. **Download Tab** — Paste video URLs or import from file, click "Download All"
2. **Browse Tab** — Pick a site & category, browse thumbnails, select videos, click "Download Selected"
3. **Queue Management** — Active downloads show progress; pending items auto-start
4. **Cancel / Cancel All** — Stop any or all downloads at any time

### Technical Details

- M3U8 stream protocol parsing & downloading
- FFmpeg TS segment merging to MP4
- `ThreadPoolExecutor` for parallel download management
- Thread-safe Tkinter queue design for GUI updates

---

### Credits

Based on [hcjohn463/JableDownload](https://github.com/hcjohn463/JableDownload) and [AlfredoUen/JableTV](https://github.com/AlfredoUen/JableTV).

### License

[Apache License 2.0](LICENSE)
