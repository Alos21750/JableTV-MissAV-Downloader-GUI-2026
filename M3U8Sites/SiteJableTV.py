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

    @classmethod
    def _get_scraper(cls):
        if cls._scraper is None:
            cls._scraper = cloudscraper.create_scraper(browser=request_headers, delay=10)
        return cls._scraper

    @classmethod
    def fetch_categories(cls):
        try:
            r = cls._get_scraper().get(f'{cls._url_root}/categories/', timeout=30)
            if r.status_code != 200: return []
            soup = BeautifulSoup(r.content, 'html.parser')
            cats = []
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
            return cats
        except Exception:
            return []

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
