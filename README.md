<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white" />
  <img src="https://img.shields.io/badge/macOS-000000?style=for-the-badge&logo=apple&logoColor=white" />
  <img src="https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black" />
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/pkgs/container/jabletv"><img src="https://img.shields.io/badge/Docker%20%2F%20NAS-2496ED?style=for-the-badge&logo=docker&logoColor=white" /></a>
  <img src="https://img.shields.io/badge/License-Apache_2.0-D22128?style=for-the-badge" />
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases"><img src="https://img.shields.io/github/downloads/Alos21750/JableTV-MissAV-Downloader-GUI-2026/total?style=for-the-badge&color=00C853&label=Downloads&logo=github&logoColor=white&cacheSeconds=86400" /></a>
</p>

<h1 align="center">JableTV Downloader — Jable TV 下載器 & MissAV 下載器 & SupJav 下載器</h1>
<p align="center"><strong>Jable TV Download GUI ｜ MissAV Download GUI ｜ SupJav Download GUI ｜ 免費桌面應用</strong></p>
<p align="center"><strong>by ALOS</strong></p>

<p align="center">
  繁體中文 ｜ <a href="./README.en.md">English</a>
</p>

> **Jable.tv 影片下載**、**MissAV 影片下載**、**SupJav 影片下載**最好用的 GUI 桌面工具，不需要命令列。提供完整的圖形介面，支援瀏覽影片、搜尋關鍵字、批量多選下載、10 路並行高速下載。同時支援 FC2、中文字幕自動篩選、女優/分類頁面一鍵全抓、M3U8/HLS 串流下載。
> **🖥️ 全平台支援**：Windows 免安裝 `.exe` 雙擊即用 · macOS / Linux 跑原始碼 · **NAS 用 Docker 無介面掛機下載**（群暉 / 威聯通等，amd64 + arm64）。
>
> The best **Jable TV downloader** with a full GUI — no CLI needed. Download videos from **Jable TV**, **MissAV**, and **SupJav** with a built-in browser, search, multi-select, and 10 parallel high-speed downloads.
> **🖥️ Cross-platform**: portable Windows `.exe`, run from source on macOS / Linux, or a **headless Docker image for your NAS** (Synology / QNAP, amd64 + arm64).

---

## 為什麼選擇 JableTV Downloader？

| | JableTV Downloader（本工具） | CLI 命令列工具 |
|--|:---:|:---:|
| 圖形介面（GUI） | **有** — 瀏覽、搜尋、點選即下載 | 無 — 需要打指令 |
| 支援 MissAV、SupJav | **有** | 通常只支援 JableTV |
| 批量下載 | **多選 + 10 路並行** | 通常一次一個 |
| 免安裝 | **雙擊 .exe 即用** | 需要安裝 Python 和套件 |
| 內建瀏覽器 | **有** — 直接在 App 裡看縮圖 | 無 |
| 進度顯示 | **即時進度條** | 終端文字 |
| 畫質選擇 | **最高/最低畫質可切換** | 通常只下載最高 |
| 跨平台 / NAS | **Windows exe · macOS / Linux · Docker（NAS）** | 多為單一平台 |
| 持續更新 | **活躍開發中** | 大多已停止維護 |

---

## 🖥️ 支援平台 / Platforms

三站（JableTV / MissAV / SupJav）在**每個平台**都通用 — 桌面挑片用 GUI，NAS 無人值守用 Docker：

| 平台 | 使用方式 | 說明 |
|------|---------|------|
| **🪟 Windows** | 免安裝 `.exe`（[Releases](../../releases)） | 雙擊即用、內建 ffmpeg、完整 GUI（**最推薦**） |
| **🍎 macOS** | `pip install -r requirements.txt` → `python main.py` | 完整 GUI（需 Python 3.8+ / Tk） |
| **🐧 Linux** | 同 macOS | 完整 GUI（需 Python 3.8+ / Tk） |
| **🐳 Docker / NAS** | `docker run … ghcr.io/alos21750/jabletv <URL>` | **無介面**批次下載，群暉 / 威聯通掛機，**amd64 + arm64** |

<sub>▸ 詳細指令見下方 [快速開始](#快速開始)。GUI 版負責瀏覽/搜尋/多選；Docker 版專為 NAS 的自動化下載而生。</sub>

---

## 螢幕截圖（「Studio Noir」介面 · 多語言 · 日 / 夜雙主題）

> 內建 **繁中 / 简中 / English / 日本語 多語言切換**、**日 / 夜雙主題**（預設跟隨 Windows 系統）。

### 🌐 首次開啟：語言選擇
<p align="center">
  <img src="./img/screenshot_language_picker.png" width="420" alt="JableTV Downloader first-run language picker — Traditional Chinese, Simplified Chinese, English, Japanese" />
</p>

### English 介面（夜間）
<p align="center">
  <img src="./img/screenshot_browse_en.png" width="800" alt="Jable TV MissAV SupJav download GUI — English interface, browse with thumbnails, dark theme" />
</p>

### 日本語 介面（夜間）
<p align="center">
  <img src="./img/screenshot_browse_ja.png" width="800" alt="Jable TV MissAV SupJav ダウンローダー — 日本語インターフェース browse dark theme" />
</p>

### 简体中文 介面（夜間）
<p align="center">
  <img src="./img/screenshot_browse_zh_hans.png" width="800" alt="JableTV MissAV SupJav 下载器 — 简体中文界面 浏览 夜间主题" />
</p>

### ☀️ 繁體中文 · 日間主題
<p align="center">
  <img src="./img/screenshot_theme_light.png" width="800" alt="JableTV MissAV SupJav 下載器 繁體中文 日間淺色主題 — light theme" />
</p>

### 下載管理（即時進度條）
<p align="center">
  <img src="./img/screenshot_download.png" width="800" alt="Jable MissAV 批量下載管理 — batch download manager with progress bars" />
</p>

### 設定頁面（語言 / 主題切換 + Cloudflare 突破）
<p align="center">
  <img src="./img/screenshot_settings.png" width="800" alt="JableTV MissAV Downloader 設定頁面 — language and theme switch, Cloudflare bypass" />
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
- **畫質選擇** — 可選最高畫質（預設）或最低畫質（省流量模式）
- **速度限制** — 可設定頻寬限制（1/2/5/10/15 MB/s 或無限制）
- **即時進度顯示** — 每部影片獨立顯示下載進度、速度、狀態（增量更新，不閃爍）
- **智慧剪貼簿** — 複製影片網址自動偵測並加入佇列
- **匯入文字檔** — 從 `.txt` / `.csv` 批量匯入網址
- **一鍵開啟資料夾** — 下載完成後直接開啟存放資料夾
- **自動合併影片** — 下載完成後自動合併 TS 片段為完整 MP4
- **斷點續傳** — 取消後可重新下載，已完成的片段不會重複下載
- **高 DPI 支援** — 自動適配高解析度螢幕，介面清晰銳利
- **設定頁面** — 可調整下載速度、儲存位置、並行數、畫質等設定
- **Windows 免安裝** — 提供打包好的 `.exe` 執行檔，不需安裝 Python

## 功能特色（Jable_smalltool.exe）

- **一次設定，每日自動** — 選一次儲存資料夾後程式自動每 24 小時檢查一次
- **支援 JableTV + MissAV + SupJav** — 可同時監控三個網站
- **完整分類池** — Jable 129、MissAV 102、SupJav 10 個穩定 ID 選項，依榜單／主分類／標籤／片商分組
- **搜尋與群組全選** — 三站分頁、群組內全選與快速篩選，避免一次掃描數百條路由
- **去重記憶** — 下載過的影片會記在 `.Jable_smalltool/seen.json`，不會重抓
- **智慧基準日期** — 預設只下載昨天之後的新片，不會在首次執行時下載大量影片
- **可隨時立即檢查** — 不想等 24 小時？點「立即檢查一次」立刻觸發
- **可背景常駐** — 最小化到工作列即可，不佔用瀏覽器

## 支援網站

| 網站 | 瀏覽 | 搜尋 | 下載 |
|------|:----:|:----:|:----:|
| [Jable.tv](https://jable.tv) | ✅ | ✅ | ✅ |
| [MissAV](https://missav.ai) | ✅ | ✅ | ✅ |
| [SupJav](https://supjav.com) | ✅ | ✅ | ✅ |
| 其他 M3U8 網站 | — | — | ✅ |

## 快速開始

### Windows 使用者（推薦）

前往 **[Releases](../../releases)** 頁面下載（每個約 58 MB，**已內建 ffmpeg，單檔雙擊即用**）：

- **JableTV_Modern.exe** — 完整下載器（瀏覽 / 搜尋 / 多選 / 並行下載）
- **Jable_smalltool.exe** — 每日自動下載小工具（設定一次資料夾即可掛機）

雙擊即可執行，**不需要安裝 Python，也不需要另外安裝 ffmpeg**。

> 🌐 **內建多語言**：繁體中文 / 简体中文 / English / 日本語，首次開啟會跳出語言選擇，之後可在右上角隨時切換（不再需要分開的英文版 exe）。

#### 🇨🇳 國內加速下載（GitHub 下載慢 / 失敗時）

GitHub Release 在中國大陸常常很慢或中斷。把下載網址前面加上鏡像前綴即可加速，**以下連結永遠指向最新版本**：

| 檔案 | 加速下載 |
|---|---|
| JableTV_Modern.exe | **[gh-proxy 加速下載](https://gh-proxy.com/https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest/download/JableTV_Modern.exe)** |
| Jable_smalltool.exe | **[gh-proxy 加速下載](https://gh-proxy.com/https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest/download/Jable_smalltool.exe)** |

> 💡 若 `gh-proxy.com` 連不上，把網址最前面的 `https://gh-proxy.com/` 換成 `https://gh-proxy.org/` 或 `https://ghfast.top/`（用法完全一樣）。真的都不行就直接開 [Releases](../../releases) 頁面下載。

### macOS / Linux / 其他平台

```bash
# 1. 確認已安裝 Python 3.8+
python --version

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 啟動完整下載器 GUI
python main.py

# 4. 啟動中文字幕自動下載小工具
python jable_smalltool.py

# 5. 命令列模式（無介面，可選）
python main.py --nogui --url "https://jable.tv/videos/abc-123/"
```

### 🐳 Docker / NAS（無介面下載，適合群暉 / 威聯通等 NAS）

映像檔由 GitHub Actions 自動建置並發佈到 GHCR（`ghcr.io/alos21750/jabletv`，支援 **amd64 / arm64**），內建 ffmpeg，支援 JableTV / MissAV / SupJav。

```bash
# 直接下載一或多個網址（影片存到主機的 ./downloads）
docker run --rm -v "$(pwd)/downloads:/downloads" \
    ghcr.io/alos21750/jabletv "https://jable.tv/videos/abc-123/"

# 或把多個網址寫進 ./downloads/urls.txt（每行一個），批次下載
docker run --rm -v "$(pwd)/downloads:/downloads" ghcr.io/alos21750/jabletv
```

用 docker-compose（NAS 最方便）：

```bash
# 把網址一行一個放進 ./downloads/urls.txt，然後：
docker compose run --rm jabletv           # 下載 urls.txt 內全部
docker compose run --rm jabletv <URL>     # 或直接指定網址
```

可用環境變數：`RESOLUTION`（highest / 1080 / 720 / 480）、`URLS_FILE`（清單路徑）、`DOWNLOAD_DIR`（容器內下載目錄，預設 `/downloads`）。
> ✅ 映像檔**已公開**，NAS 直接 `docker pull ghcr.io/alos21750/jabletv` 即可、免登入。想自行建置也行：`docker build -t jabletv .`。每次 push 或發新版 tag，GitHub Actions 會自動重建並更新 `latest`。

## 使用說明

1. **瀏覽分頁** — 選擇網站與分類，瀏覽影片縮圖，可翻頁、搜尋，勾選後點擊「下載選中」
2. **下載分頁** — 貼上影片網址或從檔案匯入，點擊「全部下載」
3. **佇列管理** — 下載中的項目會顯示進度；等候中的項目排隊自動執行
4. **設定分頁** — 調整速度限制、儲存位置、畫質偏好
5. **開啟資料夾** — 點擊「開啟資料夾」按鈕直接查看下載的影片
6. **取消 / 全部取消** — 可隨時中止下載任務

## 更新紀錄

- **v2.5.26** — 🎛️ **MissAV 同番號版本偏好可選**：SmallTool 新增「中文字幕優先／無碼流出優先／一般版優先」選項，預設為中文字幕；同番號不論版本掃描順序，都依使用者所選偏好保留一份。live 搜尋確認 `FNS-224`、`MIMK-284`、`MIDA-670` 均有 `chinese-subtitle` 版本，其中 `MIMK-284` 同時存在一般、無碼流出與中文字幕三種版本。
- **v2.5.25** — 📅 **SmallTool 番號去重與日期操作升級**：MissAV 同番號出現一般版、中文字幕版與無碼流出版時只下載一份，並固定優先保留 `uncensored-leak` 版本；日期欄新增可點選日曆與昨天、1／2／3／6 個月前快捷選項；未選儲存位置時自動建立並使用 EXE 同層的 `tmp` 資料夾。
- **v2.5.24** — 🔎 **SmallTool 監控回饋與分類操作修正**：開始監控或立即檢查後自動收合分類，主進度區會即時顯示網站、分類、掃描頁數與符合日期的候選數；分類搜尋會隱藏無結果群組，不再留下大片空白。修正監控時看似沒有動作的問題，並補上 MissAV「亂倫／NTR＋日期」完整掃描回歸測試。
- **v2.5.23** — ✦ **Modern／SmallTool 全面 UI 升級**：兩個 Windows 程式統一石墨黑、暖白與朱紅品牌視覺；Modern 瀏覽頁改為 2／3／4 欄響應式卡片、雙層工具列與分層下載列，設定頁同步提升字級與間距；SmallTool 全面改用 CustomTkinter，新增明暗主題、重整設定／分類／監控／進度／活動紀錄層級，並改善高 DPI 與窄視窗排版。
- **v2.5.22** — 🔧 **SupJav 穩定性與畫質修復**（#31）：改用可下載的 FST HLS 來源依偏好選擇 480p／720p／1080p，Streamtape 作自動備援；Range 連線中斷會從已收 byte 續傳，多線失敗時降級單線。下載失敗列新增單筆 ↻ 重試。SmallTool 新增三站完整分組分類、搜尋、群組全選與 SupJav 日期判斷。
- **v2.5.21** — 🚀 **改善 SupJav 下載速度**（#30）：Streamtape 支援 HTTP Range 時改用 4 路分段並行下載，不支援時自動保留原本單線模式；速度限制、進度與取消功能維持不變，實際速度仍依 CDN 與網路而異。GUI 與 Docker / NAS 版皆適用。
- **v2.5.20** — 🔧 **修復 SupJav 無法下載**（#29）：SupJav 的 TV 來源改用受 Google 登入保護的片段、任何非瀏覽器都抓不到（顯示「未完成」）。新版改為**優先使用 Streamtape 來源直接下載 MP4**，保留 TV（HLS）作為備援，找不到可用來源時顯示清楚訊息。GUI 與 Docker / NAS 版皆適用。
- **v2.5.19** — 🐳 **新增 Docker / NAS 版本**（#28）：headless 無介面下載器，multi-arch（amd64 + arm64）由 GitHub Actions 自動建置發佈到 `ghcr.io/alos21750/jabletv`，群暉 / 威聯通掛機超方便。同時做了一輪**全面程式碼審查與穩定性強化**：修掉剪貼簿正規表達式造成的介面卡死、自動更新器的原生崩潰風險、片段檔名碰撞導致的影片靜默損毀等，並新增 21 項單元測試（共 85 項全過）。
- **v2.5.16** — 🔄 **App 內自動更新**：啟動時背景檢查新版，一鍵下載並自動重啟（預設不更新，會先問你）；MissAV 卡片新增 無碼 / 中字 版本徽章。
- **v2.5.13 ~ 15** — 崩潰診斷（`crash_log.txt` + 原生崩潰記錄）、首次語言選擇改為非阻塞、共用單一 SSLContext 消除縮圖/下載的原生崩潰、放寬 MissAV 日期碼影片代碼。
- **v2.5.9** — 修正 MissAV 畫質選擇問題（#21）：新增 1080p／720p／480p／360p 目標選項，保留無 RESOLUTION 清單的最高／最低頻寬行為，並讓現代版 GUI 的畫質設定可跨工作階段保存。
- **v2.5.8** — 修正 MissAV 下載出現 `HTTP 403 Forbidden` 的問題（#20）：MissAV 的影片 CDN（surrit.com）已改用 Cloudflare 防護，原本以 Python 內建連線下載 m3u8／影片片段會被擋下（瀏覽縮圖正常、但一按下載就 403）。現在下載層（m3u8 播放清單、AES 金鑰、TS 片段、縮圖）改用與瀏覽頁面相同的 curl_cffi（Chrome TLS 指紋）連線，並在 CDN 被 Cloudflare 封鎖時顯示明確的「請改用 VPN/WARP」提示。JableTV／SupJav 下載不受影響。
- **v2.5.7** — 修正大型下載佇列造成啟動凍結的問題（#19）；下載清單改為限制可見列數，並以有界方式載入 / 儲存可續傳佇列；設定頁新增儲存佇列卡片，可定位或清空 `%APPDATA%\JableTV Downloader\download_queue.csv`。

## 技術細節

- M3U8 串流協定解析與多執行緒下載
- AES-128 加密串流自動解密
- 自動合併 TS 片段並封裝為可快轉 MP4（**內建 ffmpeg，免另外安裝**）
- Token-bucket 速率限制器，所有並行下載共用
- `ThreadPoolExecutor` 管理並行下載
- Tkinter 主執行緒安全佇列設計
- Per-Monitor DPI V2 高解析度支援

---

## 常見問題

**Q: 跟其他 Jable 下載工具有什麼差別？**
A: 本工具是目前唯一提供完整 GUI 圖形介面的 Jable TV / MissAV 下載器。不需要輸入命令列指令，一般使用者也能輕鬆上手。

**Q: 需要安裝 Python 嗎？**
A: Windows 使用者不需要。直接下載 `.exe` 雙擊即可執行。macOS/Linux 使用者需要 Python 3.8+。

**Q: 可以在 NAS（群暉 / 威聯通）上跑嗎？**
A: 可以，用 Docker 版即可 — `docker run --rm -v "$(pwd)/downloads:/downloads" ghcr.io/alos21750/jabletv <網址>`。這是**無介面**版本，專門給 NAS 或伺服器背景下載用，支援 amd64 與 arm64，內建 ffmpeg，三站（JableTV / MissAV / SupJav）都能下。詳見上方 [Docker / NAS](#-docker--nas無介面下載適合群暉--威聯通等-nas) 段。

**Q: 支援哪些平台？**
A: Windows（免安裝 exe）、macOS、Linux（跑原始碼）、以及 Docker / NAS（無介面）。見上方 [支援平台](#️-支援平台--platforms) 表。

**Q: 支援 MissAV 嗎？**
A: 支援。本工具同時支援 JableTV、MissAV、SupJav 三個網站的瀏覽、搜尋和下載。

---

## 免責聲明

> **本工具僅供學習與技術研究用途。** 使用者應遵守當地法律法規，尊重內容版權。開發者不對任何因使用本工具而產生的法律責任負責。請勿將本工具用於任何非法或侵權用途。

## 致謝

基於 [hcjohn463/JableDownload](https://github.com/hcjohn463/JableDownload) 及 [AlfredoUen/JableTV](https://github.com/AlfredoUen/JableTV)。

## 作者

**ALOS** — [GitHub](https://github.com/Alos21750)

## 相關搜尋 / Related Keywords

`Jable TV download` `Jable TV 下載` `JableTV downloader` `JableTV 下載器` `Jable TV downloader GUI` `Jable 影片下載` `MissAV download` `MissAV 下載` `MissAV 下載器` `MissAV downloader` `jable.tv 批量下載` `missav 批量下載` `M3U8 下載器` `M3U8 downloader` `HLS 影片下載` `HLS video download` `FC2 download` `FC2 下載` `中文字幕下載` `Chinese subtitle download` `AV downloader` `video downloader GUI` `jable tv download tool` `missav download tool` `jable downloader GUI free` `missav downloader GUI free` `jable docker` `missav docker` `jable NAS 下載` `群暉 下載 AV` `Synology jable downloader` `QNAP jable downloader` `jable downloader linux` `jable downloader macos` `docker jable tv downloader`

## Star History

<a href="https://star-history.com/#Alos21750/JableTV-MissAV-Downloader-GUI-2026&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Alos21750/JableTV-MissAV-Downloader-GUI-2026&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Alos21750/JableTV-MissAV-Downloader-GUI-2026&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Alos21750/JableTV-MissAV-Downloader-GUI-2026&type=Date" />
 </picture>
</a>

## 授權

[Apache License 2.0](LICENSE)
