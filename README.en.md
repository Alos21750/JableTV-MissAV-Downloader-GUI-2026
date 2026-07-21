<p align="center">
  <a href="./README.md">繁體中文</a> · <strong>English</strong>
</p>

<h1 align="center">JableTV Downloader</h1>

<p align="center">
  Desktop downloading and category monitoring for JableTV, MissAV, and SupJav.<br />
  Use <strong>Modern</strong> to browse and pick videos, or <strong>SmallTool</strong> to keep watching selected feeds.
</p>

<p align="center">
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/Alos21750/JableTV-MissAV-Downloader-GUI-2026?style=flat-square&label=release&color=ff5263" /></a>
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases"><img alt="Total downloads" src="https://img.shields.io/github/downloads/Alos21750/JableTV-MissAV-Downloader-GUI-2026/total?style=flat-square&label=downloads&color=2ea44f" /></a>
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026"><img alt="GitHub stars" src="https://img.shields.io/github/stars/Alos21750/JableTV-MissAV-Downloader-GUI-2026?style=flat-square&logo=github&color=f5b942" /></a>
  <a href="./LICENSE"><img alt="Apache 2.0 license" src="https://img.shields.io/github/license/Alos21750/JableTV-MissAV-Downloader-GUI-2026?style=flat-square" /></a>
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/pkgs/container/jabletv"><img alt="Docker amd64 and arm64" src="https://img.shields.io/badge/Docker-amd64%20%7C%20arm64-2496ed?style=flat-square&logo=docker&logoColor=white" /></a>
</p>

<p align="center">
  <strong><a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest/download/JableTV_Modern.exe">Download Modern</a></strong>
  ·
  <strong><a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest/download/Jable_smalltool.exe">Download SmallTool</a></strong>
  ·
  <a href="https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest">View the latest release</a>
</p>

<p align="center">
  <img src="./img/readme_modern.png" width="100%" alt="JableTV Downloader Modern v2.5.31 English dark interface with JableTV, MissAV and SupJav browse tabs" />
</p>

## Pick the right tool

| What you want to do | Choose | Workflow |
|---|---|---|
| Browse, search, and pick individual videos | **JableTV_Modern.exe** | Browse cards, multi-select, queue, or download now |
| Follow new items from selected categories | **Jable_smalltool.exe** | Choose sites, categories, a date, and version priority, then monitor |
| Run headlessly on a NAS or server | **Docker / CLI** | Pass one or more URLs, or mount a `urls.txt` file |

If you are unsure, start with **Modern**. Both Windows executables are portable, need no Python installation, and include ffmpeg in the release build.

## Windows: start in 30 seconds

1. Download [JableTV_Modern.exe](https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest/download/JableTV_Modern.exe) or [Jable_smalltool.exe](https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases/latest/download/Jable_smalltool.exe).
2. Put the file in a writable folder and double-click it.
3. Pick a language on first launch. You can later switch among English, 繁體中文, 简体中文, 日本語, plus light and dark themes.

If Windows SmartScreen appears, first verify that the file came from this project's **Releases** page, then choose “More info” → “Run anyway.”

## Modern: browse, pick, download

1. Open Browse, choose JableTV, MissAV, or SupJav, then select a category or search.
2. Select multiple cards and add them to the queue, or download the selection immediately.
3. You can also paste URLs on the Download tab or import a `.txt` / `.csv` list.
4. Use Settings for the destination, quality, concurrency, speed limit, AI subtitles, and proxy.

| Capability | Current behavior |
|---|---|
| Download queue | Per-item state, progress, and speed; queue persistence; retry one failed item |
| Concurrency | 2 jobs by default, up to 10 |
| Quality preference | Highest, 1080p, 720p, 480p, 360p, or Lowest; actual variants depend on the source |
| AI subtitles | Off, Japanese, English, Traditional Chinese, or all three as selectable sidecar SRT files |
| URL input | Clipboard detection, manual paste, and text/CSV batch import |
| Proxy | App-scoped HTTP, HTTPS, SOCKS4, and SOCKS5; no change to the Windows global proxy |
| Updates | Background GitHub Release check; the user confirms before installing an update |

## SmallTool: monitor categories automatically

<p align="center">
  <img src="./img/readme_smalltool.png" width="100%" alt="Jable SmallTool v2.5.31 Traditional Chinese dark interface showing MissAV categories, date, quality, version priority, and AI subtitles" />
</p>

1. Choose a destination. If left unset, SmallTool creates `tmp` beside the executable.
2. Pick a baseline date from the calendar, or use Yesterday / 1 / 2 / 3 / 6 months ago.
3. Choose quality and version priority: Chinese subtitles, uncensored/leak, standard, English subtitles, or reduced mosaic.
4. Choose AI subtitles: off, Japanese, English, Traditional Chinese, or all three.
5. Search and select categories on any of the three site tabs; group-wide selection is available.
6. Press Start Monitoring. The category panel collapses and progress shows the active scan or subtitle stage.

| Site | Selectable targets | Groups |
|---|---:|---|
| JableTV | 129 | Feeds/rankings, primary categories, and tag groups |
| MissAV | 102 | Feeds/rankings, categories/tags, and makers |
| SupJav | 10 | Feeds/rankings and primary categories |

SmallTool checks every 24 hours and also provides Check Now. When the same recognized title code appears across categories or sites, the candidate matching your selected version priority is kept. If a code cannot be identified reliably, only an identical URL is deduplicated—SmallTool does not guess.

State is stored in `.Jable_smalltool` beside the executable when writable, otherwise in `%APPDATA%\JableTV Downloader\smalltool`.

## AI-generated subtitles

- Both Windows GUIs offer **Off / Japanese / English / Traditional Chinese / all three** before download. They create `.ja.srt`, `.en.srt`, and `.zh-TW.srt` beside the video without modifying the MP4.
- Japanese transcription runs locally with the official [whisper.cpp](https://github.com/ggml-org/whisper.cpp). First use downloads and SHA-256-verifies the approximately 60 MB multilingual [base-q5_1 model](https://huggingface.co/ggerganov/whisper.cpp/blob/main/ggml-base-q5_1.bin) plus the [official Silero VAD](https://huggingface.co/ggml-org/whisper-vad/tree/main). The current source-language assumption is Japanese audio, and VAD skips non-speech regions.
- English and Traditional Chinese send only transcribed subtitle text to a no-key Google translation endpoint; video and audio are never uploaded. This free route has no service guarantee. On failure the video and Japanese SRT are kept, and the GUI reports the problem and offers a retry.
- Runtime depends on CPU, video length, and the amount of speech. All-three mode reuses one local transcription pass.

## Supported scope

| Site | Modern browse/search/download | SmallTool monitoring | Docker/CLI URL download |
|---|:---:|:---:|:---:|
| JableTV | ✓ | ✓ | ✓ |
| MissAV | ✓ | ✓ | ✓ |
| SupJav | ✓ | ✓ | ✓ |

Sites and CDNs can change without notice. If one stops working, update first, then open an Issue with reproducible details.

## Run from source

The current code requires **Python 3.10+** and Tk. The former Python 3.8+ README claim no longer matches syntax used by the project.

```bash
git clone https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026.git
cd JableTV-MissAV-Downloader-GUI-2026
python -m pip install -r requirements.txt

# Full GUI
python main.py

# Category monitor
python jable_smalltool.py

# One URL, no GUI
python main.py --nogui --url "https://jable.tv/videos/example/"
```

On Linux, install `python3-tk` with your system package manager if Tk is not already available. macOS and Linux run from source; the portable EXE release is for Windows.

## Docker / NAS

The public image is `ghcr.io/alos21750/jabletv:latest`. GitHub Actions builds both amd64 and arm64 variants.

```bash
# Download one URL; mount a host directory at /downloads
docker run --rm -v "/path/to/downloads:/downloads" \
  ghcr.io/alos21750/jabletv:latest "https://jable.tv/videos/example/"

# docker compose: pass a URL directly
docker compose run --rm jabletv "https://jable.tv/videos/example/"

# Or put one URL per line in ./downloads/urls.txt
docker compose run --rm jabletv
```

Environment variables:

| Variable | Purpose |
|---|---|
| `RESOLUTION` | `highest`, `1080`, `720`, `480`, `360`, or `lowest` |
| `URL` / `URLS` | Pass one or more URLs |
| `URLS_FILE` | URL list; defaults to `/downloads/urls.txt` |
| `DOWNLOAD_DIR` | Container destination; defaults to `/downloads` |

Docker is a headless, run-to-completion download job. It does not contain the Modern or SmallTool GUI.

## Troubleshooting

When opening a [GitHub Issue](https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/issues/new), include:

- App version, selected tool, and operating system.
- Site and reproducible URL, plus expected and actual behavior.
- For a crash, attach `crash_log.txt` or `crash_native.log` from beside the executable.
- Never upload cookies, proxy credentials, tokens, or other private values.

If you need a proxy, configure it in Modern Settings or at the top of SmallTool. Both GUIs share the setting, and it applies only to this application.

## Stars and project activity

<p align="center">
  <img src="./img/star-history.svg" width="100%" alt="Verified GitHub star history for JableTV Downloader" />
</p>

The chart is generated by this repository's GitHub Actions workflow. It uses a read-only repository token to request only each current stargazer's `starredAt` timestamp; usernames are neither requested nor written. The file changes only when the data or chart format changes. The curve therefore represents join dates for accounts that currently still star the repository; removed stars are not included.

<details>
<summary>Why is the old api.star-history.com image no longer embedded?</summary>

GitHub restricted access to stargazer listings in July 2026, which broke the old anonymous Star History image endpoint. This repository now generates a static SVG with its own GitHub Actions permission, avoiding a broken README image without putting a token in the README. References: [GitHub announcement](https://github.blog/changelog/2026-06-30-upcoming-access-restrictions-to-public-api-endpoints-and-ui-views/) · [Star History explanation](https://www.star-history.com/blog/github-stargazer-api-restriction/)

</details>

## License and responsible use

Code is licensed under the [Apache License 2.0](./LICENSE). Use this tool only for lawful personal or research purposes. Follow local law, site terms, and content rights, and download only material you are authorized to access.

See [Releases](https://github.com/Alos21750/JableTV-MissAV-Downloader-GUI-2026/releases) for version notes and resolved issues.

<p align="center">Built and maintained by <a href="https://github.com/Alos21750">ALOS</a>.</p>
