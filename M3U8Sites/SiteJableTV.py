#!/usr/bin/env python
# coding: utf-8

import re
import cloudscraper
from M3U8Sites.M3U8Crawler import *
from bs4 import BeautifulSoup


class SiteJableTV(M3U8Crawler):
    website_pattern = r'https://jable\.tv/videos/.+/'
    website_dirname_pattern = r'https://jable\.tv/videos/(.+)/$'

    def get_url_infos(self):
        htmlfile = cloudscraper.create_scraper(browser=request_headers, delay=10).get(self._url)
        if htmlfile.status_code != 200:
            raise Exception(f"Bad url names: {self._url}")
        result = re.search('og:title".+/>', htmlfile.text)
        self._targetName = result[0].split('"')[-2]
        result = re.search('og:image".+jpg"', htmlfile.text)
        self._imageUrl = result[0].split('"')[-2]
        result = re.search("https://.+m3u8", htmlfile.text)
        self._m3u8url = result[0]


class SiteJableTV_Backup(SiteJableTV):
    website_pattern = r'https://fs1\.app/videos/.+/'
    website_dirname_pattern = r'https://fs1\.app/videos/(.+)/$'


class JableTVList(SiteUrlList_M3U8):
    _sortby_dict = {'最高相關': '',
                   '近期最佳': 'post_date_and_popularity',
                   '最近更新': 'post_date',
                   '最多觀看': 'video_viewed',
                   '最高收藏': 'most_favourited'}

    _url_root = 'https://jable.tv'

    def __init__(self, url, silence=False):
        self.islist = None
        if not url.startswith(self._url_root): return
        self.islist = self._url_get(url)
        if self.islist is None:
            if not silence:
                print(f"網址 {url} 錯誤!!", flush=True)
            return

        titleBox = self._soup.find('div', class_='title-box')
        if titleBox and titleBox.span:
            count_text = str(titleBox.span.get_text(strip=True)).partition(" ")[0]
            self.totalLinks = int(count_text) if count_text.isdigit() else 0
        else:
            self.totalLinks = len(self.links)
        self.listType = titleBox.h2.string if titleBox and titleBox.h2 else ""

        sort_list = self._soup.find('ul', id=lambda x: x and '_sort_list' in str(x))
        if sort_list:
            activeSortType = sort_list.find('li', class_='active')
        else:
            activeSortType = self._soup.find('li', class_='active')
        if activeSortType is None: self.sortType = None
        else:  self.sortType = str(activeSortType.a.string)
        self.totalPages = (self.totalLinks + 23) // 24
        self.currentPage = 0
        self.searchKeyWord = None
        uu = url.split("/")
        if self._url_root == '/'.join(uu[0:3]):
            if len(uu)>3:
                self.url = '/'.join(uu[:-1])+'/'
                if 'search' == uu[3]:
                    self.searchKeyWord = uu[4]
        if not silence:
            print(f"[{self.listType} {str(self.sortType)}]共有{self.totalPages}頁，{self.totalLinks}部影片。已取得{len(self.links)}部影片")

    def _url_get(self, url):
        divlist = None
        try:
            htmlfile = cloudscraper.create_scraper(browser=request_headers, delay=10).get(url)
            if htmlfile.status_code == 200:
                content = htmlfile.content
                soup = BeautifulSoup(content, 'html.parser')
                self._soup = soup
                divlist = soup.find('div', id=lambda x: x and x.startswith('list_videos'))
                if divlist is None:
                    divlist = soup.find('div', id="site-content")
                    if divlist: divlist = divlist.div
                divlists_MemberOnly = soup.find_all('div', class_="ribbon-top-left")
                _memberOnly_urls = [del_url.find_parent('a')['href'] for del_url in divlists_MemberOnly if del_url.getText() == '會員']
                if divlist is None: return None
                self.links = []
                self.linkDescriptions = []
                self.thumbnails = []
                tags = divlist.select('div.detail')
                for tag in tags:
                    if not tag.h6 or not tag.h6.a: continue
                    tag_a = tag.h6.a
                    _url = tag_a['href']
                    if _url not in _memberOnly_urls:
                        self.links.append(_url)
                        self.linkDescriptions.append(str(tag_a.string or ''))
                        card = tag.find_parent('div', class_='video-img-box')
                        thumb = ''
                        if card:
                            img = card.select_one('img')
                            if img:
                                thumb = img.get('data-src', '') or img.get('src', '')
                        self.thumbnails.append(thumb)
            return divlist

        except Exception:
            return divlist

    def getSortTypeList(self):
        ll = list(JableTVList._sortby_dict)
        if self.searchKeyWord is None: del ll[0]
        return ll

    def getThumbnails(self):
        return getattr(self, 'thumbnails', [])

    def loadPageAtIndex(self, index, sortby):
        if self.currentPage == index:
            if self.sortType is None: return
            if self.sortType == sortby: return

        if self.sortType is None:
            if self.searchKeyWord is None:
                newUrl = self.url + f"?from={index+1}"
            else:
                newUrl = f"{self._url_root}/search/?q={self.searchKeyWord}&from_videos={index+1}"
        else:
            if self.searchKeyWord is None:
                newUrl = self.url + f"?sort_by={JableTVList._sortby_dict[sortby]}&from={index+1}"
            else:
                newUrl = f"{self._url_root}/search/?q={self.searchKeyWord}&sort_by={JableTVList._sortby_dict[sortby]}&from_videos={index+1}"
        self._url_get(newUrl)
        self.currentPage = index
        self.sortType = sortby


class JableTVBrowser:
    """Fetches categories and video listings from jable.tv for the browse GUI."""
    _url_root = 'https://jable.tv'
    _scraper = None

    # ── Homepage sections (prepended to category list) ───────────────────
    HOMEPAGE_SECTIONS = [
        ('最近更新', 'https://jable.tv/latest-updates/'),
        ('熱門影片', 'https://jable.tv/hot/'),
        ('新片上架', 'https://jable.tv/new-release/'),
    ]

    # ── Hot section time filters ─────────────────────────────────────────
    HOT_TIME_FILTERS = {
        '所有時間': '',
        '今日熱門': 't=today',
        '本週熱門': 't=week',
        '本月熱門': 't=month',
    }

    # ── Sidebar tags (mirrors jable.tv left sidebar) ─────────────────────
    SIDEBAR_TAGS = {
        '衣著': [
            ('黑絲', 'black-pantyhose'), ('過膝襪', 'knee-socks'),
            ('運動裝', 'sportswear'), ('肉絲', 'flesh-toned-pantyhose'),
            ('絲襪', 'pantyhose'), ('眼鏡娘', 'glasses'),
            ('獸耳', 'kemonomimi'), ('漁網', 'fishnets'),
            ('水着', 'swimsuit'), ('校服', 'school-uniform'),
            ('旗袍', 'cheongsam'), ('婚紗', 'wedding-dress'),
            ('女僕', 'maid'), ('和服', 'kimono'),
            ('吊帶襪', 'stockings'), ('兔女郎', 'bunny-girl'),
            ('Cosplay', 'Cosplay'),
        ],
        '身材': [
            ('黑肉', 'suntan'), ('長身', 'tall'),
            ('軟體', 'flexible-body'), ('貧乳', 'small-tits'),
            ('美腿', 'beautiful-leg'), ('美尻', 'beautiful-butt'),
            ('紋身', 'tattoo'), ('短髮', 'short-hair'),
            ('白虎', 'hairless-pussy'), ('熟女', 'mature-woman'),
            ('巨乳', 'big-tits'), ('少女', 'girl'),
            ('嬌小', 'dainty'),
        ],
        '交合': [
            ('顏射', 'facial'), ('腳交', 'footjob'),
            ('肛交', 'anal-sex'), ('痙攣', 'spasms'),
            ('潮吹', 'squirting'), ('深喉', 'deep-throat'),
            ('接吻', 'kiss'), ('口爆', 'cum-in-mouth'),
            ('口交', 'blowjob'), ('乳交', 'tit-wank'),
            ('中出', 'creampie'),
        ],
        '玩法': [
            ('露出', 'outdoor'), ('集團進犯', 'gang-intrusion'),
            ('進犯', 'intrusion'), ('調教', 'tune'),
            ('綑綁', 'bondage'), ('瞬間插入', 'quickie'),
            ('痴漢', 'chikan'), ('痴女', 'chizyo'),
            ('男M', 'masochism-guy'), ('泥醉', 'crapulence'),
            ('泡姬', 'soapland'), ('母乳', 'breast-milk'),
            ('放尿', 'piss'), ('按摩', 'massage'),
            ('多P', 'groupsex'), ('刑具', 'grip'),
            ('凌辱', 'insult'), ('一日十回', '10-times-a-day'),
            ('3P', '3p'),
        ],
        '劇情': [
            ('黑人', 'black'), ('醜男', 'ugly-man'),
            ('誘惑', 'temptation'), ('親屬', 'kinship'),
            ('童貞', 'virginity'), ('時間停止', 'time-stop'),
            ('復仇', 'avenge'), ('年齡差', 'age-difference'),
            ('巨漢', 'giant'), ('媚藥', 'love-potion'),
            ('夫目前犯', 'sex-beside-husband'), ('出軌', 'affair'),
            ('催眠', 'hypnosis'), ('偷拍', 'private-cam'),
            ('下雨天', 'rainy-day'), ('NTR', 'ntr'),
        ],
        '角色': [
            ('風俗娘', 'club-hostess-and-sex-worker'), ('醫生', 'doctor'),
            ('逃犯', 'fugitive'), ('護士', 'nurse'),
            ('老師', 'teacher'), ('空姐', 'flight-attendant'),
            ('球隊經理', 'team-manager'), ('未亡人', 'widow'),
            ('搜查官', 'detective'), ('情侶', 'couple'),
            ('家政婦', 'housewife'), ('家庭教師', 'private-teacher'),
            ('偶像', 'idol'), ('人妻', 'wife'),
            ('主播', 'female-anchor'), ('OL', 'ol'),
        ],
        '地點': [
            ('魔鏡號', 'magic-mirror'), ('電車', 'tram'),
            ('處女', 'first-night'), ('監獄', 'prison'),
            ('溫泉', 'hot-spring'), ('洗浴場', 'bathing-place'),
            ('泳池', 'swimming-pool'), ('汽車', 'car'),
            ('廁所', 'toilet'), ('學校', 'school'),
            ('圖書館', 'library'), ('健身房', 'gym-room'),
            ('便利店', 'store'),
        ],
        '雜項': [
            ('錄像', 'video-recording'), ('處女作/引退作', 'debut-retires'),
            ('綜藝', 'variety-show'), ('節日主題', 'festival'),
            ('感謝祭', 'thanksgiving'), ('4小時以上', 'more-than-4-hours'),
        ],
    }

    @classmethod
    def _get_scraper(cls):
        if cls._scraper is None:
            cls._scraper = cloudscraper.create_scraper(browser=request_headers, delay=10)
        return cls._scraper

    @classmethod
    def tag_url(cls, slug):
        return f'{cls._url_root}/tags/{slug}/'

    @classmethod
    def fetch_categories(cls):
        """Return homepage sections + dynamic categories from /categories/."""
        cats = [{'name': name, 'url': url, 'count': 0, 'section': True}
                for name, url in cls.HOMEPAGE_SECTIONS]
        try:
            r = cls._get_scraper().get(f'{cls._url_root}/categories/', timeout=30)
            if r.status_code != 200:
                return cats
            soup = BeautifulSoup(r.content, 'html.parser')
            for a in soup.select('a[href*="/categories/"]'):
                href = a.get('href', '')
                text = a.get_text(strip=True)
                if '/categories/' in href and href != f'{cls._url_root}/categories/' and text:
                    name = text
                    count_match = re.search(r'(\d[\d,]*)\s*部影片', text)
                    count = int(count_match.group(1).replace(',', '')) if count_match else 0
                    name = re.sub(r'\d[\d,]*\s*部影片', '', name).strip()
                    slug = href.rstrip('/').split('/')[-1]
                    cats.append({'name': name, 'slug': slug, 'url': href, 'count': count})
        except Exception:
            pass
        return cats

    @classmethod
    def fetch_page(cls, url):
        try:
            r = cls._get_scraper().get(url, timeout=30)
            if r.status_code != 200: return []
            soup = BeautifulSoup(r.content, 'html.parser')
            divlist = soup.find('div', id=lambda x: x and x.startswith('list_videos'))
            if divlist is None: return []
            cards = divlist.select('div.video-img-box')
            videos = []
            for card in cards:
                detail = card.select_one('div.detail')
                if not detail or not detail.h6 or not detail.h6.a: continue
                tag_a = detail.h6.a
                img = card.select_one('img')
                duration_span = card.select_one('span.label')
                videos.append({
                    'url': tag_a.get('href', ''),
                    'title': str(tag_a.string or ''),
                    'thumbnail': img.get('data-src', '') if img else '',
                    'duration': duration_span.string if duration_span else '',
                })
            return videos
        except Exception:
            return []

    @classmethod
    def fetch_sidebar_tags(cls):
        """Return the sidebar tag structure for the browse UI."""
        result = {}
        for group, tags in cls.SIDEBAR_TAGS.items():
            result[group] = [{'name': name, 'slug': slug,
                              'url': cls.tag_url(slug)} for name, slug in tags]
        return result
