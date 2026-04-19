<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Downloads-10_Parallel-00C853?style=for-the-badge" />
</p>

<h1 align="center">JableTV & MissAV Downloader — Material Design 2026</h1>
<p align="center"><strong>Jable TV 下載器 ｜ MissAV 下載器 ｜ GUI 桌面應用程式</strong></p>
<p align="center"><strong>by ALOS</strong></p>

<p align="center">
  繁體中文 ｜ <a href="./README.en.md">English</a>
</p>

> **Jable.tv 影片下載**、**MissAV 影片下載**的最佳桌面工具。提供完整的圖形介面（GUI），支援瀏覽影片、搜尋關鍵字、批量多選下載、10 路並行高速下載。免安裝 Windows 執行檔，雙擊即用。同時支援 FC2、中文字幕自動篩選、女優/分類頁面一鍵全抓。
>
> The best desktop tool for downloading videos from **Jable TV** and **MissAV**. Full GUI with built-in browser, search, multi-select, and 10 parallel high-speed downloads. Portable Windows `.exe` — no installation required.

---

## 螢幕截圖（Material Design 原生介面）

### JableTV 瀏覽頁面
<p align="center">
  <img src="./img/screenshot_browse_jable.png" width="800" alt="Jable TV 下載器 GUI 瀏覽頁面 — JableTV Downloader browse interface" />
</p>

### MissAV 瀏覽頁面
<p align="center">
  <img src="./img/screenshot_browse_missav.png" width="800" alt="MissAV 下載器 GUI 瀏覽頁面 — MissAV Downloader browse interface" />
</p>

### 下載管理（即時進度條）
<p align="center">
  <img src="./img/screenshot_download.png" width="800" alt="Jable MissAV 批量下載管理 — batch download manager with progress bars" />
</p>

### 設定頁面
<p align="center">
  <img src="./img/screenshot_settings.png" width="800" alt="JableTV MissAV Downloader 設定頁面 — settings page" />
</p>

---

## 兩個工具

本專案提供兩個獨立的執行檔：

| 工具 | 用途 | 適用對象 |
|------|------|----------|
| **JableTV_Modern.exe** | 完整下載器 — 瀏覽、搜尋、多選、並行下載 | 想要主動挑選影片並下載的使用者 |
| **Jable_smalltool.exe** | 每日自動下載 `中文字幕` 新片 — 設定一次資料夾即可掛機 | 想要背景自動抓最新中文字幕片的使用者 |

## 功能特色（JableTV_Modern.exe）

- **Material Design 原生介面** — 採用 CustomTkinter 打造，深色主題，無需瀏覽器
- **內建瀏覽器** — 直接在應用程式內瀏覽影片分類、搜尋關鍵字，支援翻頁瀏覽
- **多選下載** — 在瀏覽頁面勾選多部影片，一鍵送入下載佇列
- **並行下載（最多 10 路）** — 同時下載最多 10 部影片，可於設定頁調整（預設 2）
- **速度限制** — 可設定頻寬限制（1/2/5/10/15 MB/s 或無限制）
- **即時進度顯示** — 每部影片獨立顯示下載進度、速度、狀態（增量更新，不閃爍）
- **智慧剪貼簿** — 複製影片網址自動偵測並加入佇列
- **匯入文字檔** — 從 `.txt` / `.csv` 批量匯入網址
- **一鍵開啟資料夾** — 下載完成後直接開啟存放資料夾
- **自動合併影片** — 下載完成後自動合併 TS 片段為完整 MP4
- **斷點續傳** — 取消後可重新下載，已完成的片段不會重複下載
- **高 DPI 支援** — 自動適配高解析度螢幕，介面清晰銳利
- **設定頁面** — 可調整下載速度、儲存位置、並行數等設定
- **Windows 免安裝** — 提供打包好的 `.exe` 執行檔，不需安裝 Python

## 功能特色（Jable_smalltool.exe）

- **一次設定，每日自動** — 選一次儲存資料夾後程式自動每 24 小時檢查一次
- **鎖定中文字幕** — 只抓 `jable.tv/tags/chinese-subtitle/` 的新片
- **去重記憶** — 下載過的影片會記在 `.Jable_smalltool/seen.json`，不會重抓
- **首次執行回補** — 第一次執行會掃 3 頁補齊近期新片，之後每天只掃 2 頁
- **可隨時立即檢查** — 不想等 24 小時？點「立即檢查一次」立刻觸發
- **可背景常駐** — 最小化到工作列即可，不佔用瀏覽器

## 支援網站

| 網站 | 瀏覽 | 搜尋 | 下載 |
|------|:----:|:----:|:----:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ai) | ✅ | ✅ | ✅ |
| 其他 M3U8 網站 | — | — | ✅ |

## 快速開始

### 🖥️ Windows 使用者（推薦）

前往 **[Releases](../../releases)** 頁面下載：

- **JableTV_Modern.exe** — 完整下載器（約 27 MB）
- **Jable_smalltool.exe** — 中文字幕每日自動下載小工具（約 21 MB）

雙擊即可執行，**不需要安裝 Python**。

### 🐍 macOS / Linux / 其他平台

```bash
# 1. 確認已安裝 Python 3.8+
python --version

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 啟動完整下載器 GUI
python main.py

# 4. 啟動中文字幕自動下載小工具
python jable_smalltool.py

# 5. 命令列模式（可選）
python main.py -nogui True
```

## 使用說明

1. **瀏覽分頁** — 選擇網站與分類，瀏覽影片縮圖，可翻頁、搜尋，勾選後點擊「下載選中」
2. **下載分頁** — 貼上影片網址或從檔案匯入，點擊「全部下載」
3. **佇列管理** — 下載中的項目會顯示進度；等候中的項目排隊自動執行
4. **設定分頁** — 調整速度限制、儲存位置
5. **開啟資料夾** — 點擊「開啟資料夾」按鈕直接查看下載的影片
6. **取消 / 全部取消** — 可隨時中止下載任務

## 技術細節

- M3U8 串流協定解析與多執行緒下載
- AES-128 加密串流自動解密
- 自動合併 TS 片段為 MP4（無需 FFmpeg）
- Token-bucket 速率限制器，所有並行下載共用
- `ThreadPoolExecutor` 管理並行下載
- Tkinter 主執行緒安全佇列設計
- Per-Monitor DPI V2 高解析度支援

---

## 免責聲明

> **本工具僅供學習與技術研究用途。** 使用者應遵守當地法律法規，尊重內容版權。開發者不對任何因使用本工具而產生的法律責任負責。請勿將本工具用於任何非法或侵權用途。

## 致謝

基於 [hcjohn463/JableDownload](https://github.com/hcjohn463/JableDownload) 及 [AlfredoUen/JableTV](https://github.com/AlfredoUen/JableTV)。

## 作者

**ALOS** — [GitHub](https://github.com/Alos21750)

## 相關搜尋 / Related Keywords

`Jable TV 下載` `JableTV 下載器` `Jable 影片下載` `MissAV 下載` `MissAV 下載器` `Jable download` `MissAV download` `Jable TV downloader GUI` `MissAV downloader` `jable.tv 批量下載` `missav 批量下載` `M3U8 下載器` `HLS 影片下載` `FC2 下載` `中文字幕下載` `AV downloader` `video downloader GUI` `jable tv download tool` `missav download tool`

## 授權

[Apache License 2.0](LICENSE)
