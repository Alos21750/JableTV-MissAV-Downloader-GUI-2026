<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Downloads-10_Parallel-00C853?style=for-the-badge" />
</p>

<h1 align="center">JableTV & MissAV Downloader GUI 2026</h1>

<p align="center">
  <a href="#繁體中文">繁體中文</a> ｜ <a href="#english">English</a>
</p>

---

## Screenshots

### JableTV 瀏覽頁面 / Browse
<p align="center">
  <img src="./img/screenshot_browse_jable.png" width="800" alt="JableTV Browse" />
</p>

### MissAV 瀏覽頁面 / Browse
<p align="center">
  <img src="./img/screenshot_browse_missav.png" width="800" alt="MissAV Browse" />
</p>

### 下載管理 / Download Manager
<p align="center">
  <img src="./img/screenshot_download.png" width="800" alt="Download Manager" />
</p>

---

# 繁體中文

## 功能特色

- **內建瀏覽器** — 直接在應用程式內瀏覽影片分類、搜尋關鍵字，支援翻頁瀏覽
- **多選下載** — 在瀏覽頁面勾選多部影片，一鍵送入下載佇列
- **10 路並行下載** — 同時下載最多 10 部影片，超出自動排隊等候
- **即時進度顯示** — 每部影片獨立顯示下載進度、速度、狀態
- **智慧剪貼簿** — 複製影片網址自動偵測並加入佇列
- **匯入文字檔** — 從 `.txt` / `.csv` 批量匯入網址
- **一鍵開啟資料夾** — 下載完成後直接開啟存放資料夾
- **自動合併影片** — 下載完成後自動合併 TS 片段為完整 MP4
- **斷點續傳** — 取消後可重新下載，已完成的片段不會重複下載
- **高 DPI 支援** — 自動適配高解析度螢幕，介面清晰銳利
- **Windows 免安裝** — 提供打包好的 `.exe` 執行檔，不需安裝 Python

## 支援網站

| 網站 | 瀏覽 | 搜尋 | 下載 |
|------|:----:|:----:|:----:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ai) | ✅ | ✅ | ✅ |
| 其他 M3U8 網站 | — | — | ✅ |

## 快速開始

### 🖥️ Windows 使用者（推薦）

前往 **[Releases](../../releases)** 頁面，下載最新版 `windowsGUI.exe`，雙擊即可執行，**不需要安裝 Python**。

### 🐍 macOS / Linux / 其他平台

```bash
# 1. 確認已安裝 Python 3.8+
python --version

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 啟動圖形介面
python main.py

# 4. 命令列模式（可選）
python main.py -nogui True
```

## 使用說明

1. **瀏覽分頁** — 選擇網站與分類，瀏覽影片縮圖，可翻頁、搜尋，勾選後點擊「下載選中」
2. **下載分頁** — 貼上影片網址或從檔案匯入，點擊「全部下載」
3. **佇列管理** — 下載中的項目會顯示進度；等候中的項目排隊自動執行
4. **開啟資料夾** — 點擊「開啟資料夾」按鈕直接查看下載的影片
5. **取消 / 全部取消** — 可隨時中止下載任務

## 技術細節

- M3U8 串流協定解析與多執行緒下載
- AES-128 加密串流自動解密
- 自動合併 TS 片段為 MP4（無需 FFmpeg）
- `ThreadPoolExecutor` 管理並行下載
- Tkinter 主執行緒安全佇列設計
- Per-Monitor DPI V2 高解析度支援

---

# English

## Features

- **Built-in Browser** — Browse video categories and search directly within the app, with full pagination
- **Multi-Select Download** — Check multiple videos in the browse panel, send to download queue in one click
- **10 Parallel Downloads** — Download up to 10 videos simultaneously; extras auto-queue
- **Real-Time Progress** — Individual progress, speed & status for each download
- **Smart Clipboard** — Auto-detects video URLs copied to clipboard
- **Import from File** — Batch-import URLs from `.txt` / `.csv` files
- **Open Folder** — One-click to open the download destination folder
- **Auto Merge** — Automatically merges TS segments into a complete MP4 after download
- **Resume Support** — Cancelled downloads can be restarted; completed segments are preserved
- **High DPI Support** — Automatically adapts to high-resolution displays for crisp UI
- **Portable Windows Build** — Pre-packaged `.exe`, no Python installation needed

## Supported Sites

| Site | Browse | Search | Download |
|------|:------:|:------:|:--------:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ai) | ✅ | ✅ | ✅ |
| Other M3U8 sites | — | — | ✅ |

## Quick Start

### 🖥️ Windows Users (Recommended)

Go to **[Releases](../../releases)** and download the latest `windowsGUI.exe`. Double-click to run — **no Python installation needed**.

### 🐍 macOS / Linux / Other Platforms

```bash
# 1. Make sure Python 3.8+ is installed
python --version

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch GUI
python main.py

# 4. CLI mode (optional)
python main.py -nogui True
```

## Usage

1. **Browse Tab** — Pick a site & category, browse thumbnails with pagination, select videos, click "Download Selected"
2. **Download Tab** — Paste video URLs or import from file, click "Download All"
3. **Queue Management** — Active downloads show progress; pending items auto-start
4. **Open Folder** — Click the folder button to view downloaded videos
5. **Cancel / Cancel All** — Stop any or all downloads at any time

## Technical Details

- M3U8 stream protocol parsing & multi-threaded download
- AES-128 encrypted stream auto-decryption
- Automatic TS segment merging to MP4 (no FFmpeg required)
- `ThreadPoolExecutor` for parallel download management
- Thread-safe Tkinter queue design for GUI updates
- Per-Monitor DPI V2 support for high-resolution displays

---

## Credits

Based on [hcjohn463/JableDownload](https://github.com/hcjohn463/JableDownload) and [AlfredoUen/JableTV](https://github.com/AlfredoUen/JableTV).

## License

[Apache License 2.0](LICENSE)
