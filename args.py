import argparse
from bs4 import BeautifulSoup
import random
from urllib.request import Request, urlopen
from config import headers
import re


def get_parser():
    parser = argparse.ArgumentParser(description="JableTV & MissAV Downloader — by ALOS")
    # store_true, not type=bool: argparse's bool("False") is truthy, so `--nogui False`
    # would wrongly enable it. store_true makes the mere presence of the flag mean True.
    parser.add_argument("--random", action='store_true',
                        help="Download a random recommended video")
    parser.add_argument("--url", type=str, default="",
                        help="Jable TV URL to download")
    parser.add_argument("--nogui", action='store_true',
                        help="Disable GUI mode")

    return parser


def av_recommand():
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = 'https://jable.tv/'
    request = Request(url, headers=headers)
    try:
        web_content = urlopen(request, timeout=15).read()  # timeout: never hang forever
    except Exception:
        return None
    # 得到繞過轉址後的 html
    soup = BeautifulSoup(web_content, 'html.parser')
    h6_tags = soup.find_all('h6', class_='title')
    av_list = re.findall(r'https[^"]+', str(h6_tags))
    if not av_list:              # site changed/blocked -> avoid random.choice([]) IndexError
        return None
    return random.choice(av_list)


# print(av_recommand())
