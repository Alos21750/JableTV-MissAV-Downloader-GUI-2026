#!/usr/bin/env python
# coding: utf-8
"""Localization strings for the GUI apps."""

STRINGS = {
    'zh': {
        # Header
        'app_brand_1': 'JableTV & MissAV',
        'app_brand_2': 'Downloader',
        'version_label': 'v2.1 Professional',
        'by_author': 'by ALOS',

        # Tabs
        'tab_browse': '瀏覽',
        'tab_download': '下載',
        'tab_settings': '設定',

        # Browse tab
        'browse_category': '瀏覽選片',
        'category_label': '分類:',
        'sort_latest': '最近更新',
        'search_placeholder': '加入搜尋',
        'search_btn': '搜尋',
        'download_selected': '下載選中',
        'select_all_btn': '全選',
        'first_page': '« 首頁',
        'prev_page': '< 上一頁',
        'page_n': '第 {n} 頁',
        'next_page': '下一頁 >',
        'select': '選取',
        'selected': '已選中',
        'url_not_supported': '不支援的網址',
        'crawling_url': '正在抓取列表...',
        'crawl_added': '已加入 {n} 部影片到下載清單',
        'loading_browse': '載入中...',
        'no_results': '沒有找到影片',
        'fetch_error': '載入失敗，請稍後再試',

        # Download tab
        'save_location': '存放位置',
        'url_label': '下載網址',
        'browse_folder': '瀏覽',
        'download_btn': '▶ 下載',
        'download_all_btn': '▶▶ 全部下載',
        'cancel_all': '全部取消',
        'clear_list': '清單',
        'browse_import': '瀏覽 已選中 開啟',
        'speed_limit': '速度',
        'unlimited': '無限制',
        'concurrent': '同時下載數',
        'max_n': '最多 {n} 個',

        # Download states
        'state_downloading': '下載中',
        'state_waiting': '等待中',
        'state_downloaded': '已下載',
        'state_cancelled': '已取消',
        'state_error': '錯誤',
        'state_merging': '合併中',

        # Settings tab
        'settings_title': '設定',
        'settings_desc': '管理下載偏好設定與應用程式資訊',
        'download_settings': '下載設定',
        'save_location_setting': '存放位置',
        'save_location_desc': '配置下載文件的預設儲存目錄',
        'speed_limit_setting': '速度限制',
        'speed_limit_desc': '限制每個下載任務的最大頻寬',
        'concurrent_setting': '同時下載數',
        'concurrent_desc': '同時進行的下載任務數量，過多可能降低單個下載速度',
        'about': '關於',
        'app_full_name': 'JableTV & MissAV Downloader',
        'disclaimer': '僅供學習與研究用途',

        # Smalltool
        'st_title': '多站自動下載工具',
        'st_header': 'Jable 小工具',
        'st_header_sub': '多站自動下載',
        'st_save_location': '儲存位置:',
        'st_browse': '瀏覽',
        'st_baseline_date': '基準日期:',
        'st_date_hint': '(YYYY-MM-DD，只下載此日期之後的影片)',
        'st_select_hint': '選擇網站與分類（可多選）:',
        'st_select_all': '全選',
        'st_start': '▶ 啟動背景偵測',
        'st_stop': '■ 停止',
        'st_check_now': '↻ 立即檢查一次',
        'st_idle': '閒置',
        'st_running': '● 執行中',
        'st_stopped': '已停止',
        'st_footer': '提示：關閉視窗會結束程式。最小化後程式仍在背景運行。每 24 小時自動檢查一次。',
        'st_no_folder': '缺少資料夾',
        'st_no_folder_msg': '請先選擇影片儲存資料夾。',
        'st_no_cat': '未選擇分類',
        'st_no_cat_msg': '請至少勾選一個網站分類。',
        'st_bad_date': '日期格式錯誤',
        'st_bad_date_msg': '基準日期格式應為 YYYY-MM-DD。',
        'st_started_msg': '背景偵測已啟動 — 你可以將視窗最小化。',

        # MissAV language prefix for URLs
        'missav_lang': 'cn',
    },
    'en': {
        # Header
        'app_brand_1': 'JableTV & MissAV',
        'app_brand_2': 'Downloader',
        'version_label': 'v2.1 Professional',
        'by_author': 'by ALOS',

        # Tabs
        'tab_browse': 'Browse',
        'tab_download': 'Download',
        'tab_settings': 'Settings',

        # Browse tab
        'browse_category': 'Browse Videos',
        'category_label': 'Category:',
        'sort_latest': 'Latest',
        'search_placeholder': 'Search...',
        'search_btn': 'Search',
        'download_selected': 'Download Selected',
        'select_all_btn': 'Select All',
        'first_page': '« First',
        'prev_page': '< Prev',
        'page_n': 'Page {n}',
        'next_page': 'Next >',
        'select': 'Select',
        'selected': 'Selected',
        'loading_browse': 'Loading...',
        'no_results': 'No videos found',
        'fetch_error': 'Failed to load, please try again',
        'url_not_supported': 'Unsupported URL',
        'crawling_url': 'Crawling listing...',
        'crawl_added': 'Added {n} videos to download queue',

        # Download tab
        'save_location': 'Save to',
        'url_label': 'Video URL',
        'browse_folder': 'Browse',
        'download_btn': '▶ Download',
        'download_all_btn': '▶▶ Download All',
        'cancel_all': 'Cancel All',
        'clear_list': 'Clear',
        'browse_import': 'Browse Selected Open',
        'speed_limit': 'Speed',
        'unlimited': 'Unlimited',
        'concurrent': 'Concurrent',
        'max_n': 'Max {n}',

        # Download states
        'state_downloading': 'Downloading',
        'state_waiting': 'Waiting',
        'state_downloaded': 'Downloaded',
        'state_cancelled': 'Cancelled',
        'state_error': 'Error',
        'state_merging': 'Merging',

        # Settings tab
        'settings_title': 'Settings',
        'settings_desc': 'Manage download preferences and app info',
        'download_settings': 'Download Settings',
        'save_location_setting': 'Save Location',
        'save_location_desc': 'Configure the default download directory',
        'speed_limit_setting': 'Speed Limit',
        'speed_limit_desc': 'Limit the maximum bandwidth per download task',
        'concurrent_setting': 'Concurrent Downloads',
        'concurrent_desc': 'Number of simultaneous downloads; too many may reduce individual speed',
        'about': 'About',
        'app_full_name': 'JableTV & MissAV Downloader',
        'disclaimer': 'For educational and research purposes only',

        # Smalltool
        'st_title': 'Multi-Site Auto Downloader',
        'st_header': 'Jable Tool',
        'st_header_sub': 'Multi-Site Auto Download',
        'st_save_location': 'Save to:',
        'st_browse': 'Browse',
        'st_baseline_date': 'After date:',
        'st_date_hint': '(YYYY-MM-DD, only download videos after this date)',
        'st_select_hint': 'Select sites and categories (multi-select):',
        'st_select_all': 'Select All',
        'st_start': '▶ Start Monitoring',
        'st_stop': '■ Stop',
        'st_check_now': '↻ Check Now',
        'st_idle': 'Idle',
        'st_running': '● Running',
        'st_stopped': 'Stopped',
        'st_footer': 'Tip: Closing the window stops the program. Minimize to keep it running. Auto-checks every 24 hours.',
        'st_no_folder': 'No Folder',
        'st_no_folder_msg': 'Please select a download folder first.',
        'st_no_cat': 'No Category',
        'st_no_cat_msg': 'Please select at least one site category.',
        'st_bad_date': 'Invalid Date',
        'st_bad_date_msg': 'Date format should be YYYY-MM-DD.',
        'st_started_msg': 'Monitoring started — you can minimize this window.',

        # MissAV language prefix for URLs
        'missav_lang': 'en',
    },
}

# Active language — set before GUI init
_current_lang = 'zh'


def set_lang(lang: str):
    global _current_lang
    _current_lang = lang if lang in STRINGS else 'zh'


def T(key: str, **kwargs) -> str:
    """Translate a key to the current language."""
    s = STRINGS.get(_current_lang, STRINGS['zh']).get(key, key)
    if kwargs:
        return s.format(**kwargs)
    return s


def get_lang() -> str:
    return _current_lang
