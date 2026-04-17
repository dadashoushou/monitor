"""
批量检测书签网站是否有 RSS feed
输出：有RSS的网站列表 + 无RSS的网站列表
"""

import sys
import time
import requests
import feedparser
from html.parser import HTMLParser
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── 1. 解析书签文件 ──────────────────────────────────────────────

class BookmarkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current_href = None
        self.current_text = ''
        self.in_a = False

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current_href = dict(attrs).get('href', '')
            self.in_a = True
            self.current_text = ''

    def handle_endtag(self, tag):
        if tag == 'a' and self.in_a:
            self.links.append((self.current_href, self.current_text.strip()))
            self.in_a = False

    def handle_data(self, data):
        if self.in_a:
            self.current_text += data


def extract_sites(bookmark_file):
    """从书签文件提取唯一域名，返回 {domain: (url, title)}"""
    with open(bookmark_file, 'r', encoding='utf-8') as f:
        content = f.read()

    parser = BookmarkParser()
    parser.feed(content)

    # 过滤掉工具类、搜索引擎、单篇文章等
    skip_keywords = [
        'baidu', 'sogou', 'wikipedia', 'twitter', 'facebook', 'youtube',
        'google', 'bing.com', 'bd.ykdfr', 'dpzai', 'careerengine', 'csdn',
        'zhihu', 'zhuanlan', 'eventbrite', 'airport-data', 'airteamimages',
        'jetphotos', 'planefinder', 'flightaware', 'satbeams', 'motortrend',
        'businesswire', 'sttinfo', 'notams.aim', '30ttq', 'qusecure',
        'weforum', 'npl.co.uk', 'phys.org', 'byteclicks', 'hypeaviation',
        'taodocs', 'wenku.so', 'yazbk', 'hiduba', 'ydyxfo', 'avfoil',
        'helicoptermaintenancem', 'careerengine', '47.117', 'aeroinfo.com.cn',
        'chinaports.com', 'kemenhub.go.id', '12377.cn', 'posts.careerengine',
    ]

    sites = {}
    for href, title in parser.links:
        if not href.startswith('http'):
            continue
        if any(k in href.lower() for k in skip_keywords):
            continue
        domain = urlparse(href).netloc
        if domain and domain not in sites:
            # 只保留根域名的 URL（去掉子页面路径，方便检测 RSS）
            root_url = f"{urlparse(href).scheme}://{domain}/"
            sites[domain] = (root_url, title)

    return sites


# ── 2. RSS 检测逻辑 ──────────────────────────────────────────────

# 常见 RSS 路径
RSS_PATHS = [
    'feed', 'feed/', 'rss', 'rss/', 'rss.xml', 'feed.xml',
    'atom.xml', 'index.xml', 'feeds/all.atom.xml',
    'news/rss', 'news/feed', 'blog/feed', 'blog/rss',
    'articles/feed', 'publications/feed',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; RSS-checker/1.0)',
}

def is_valid_feed(url, timeout=4):
    """检测 URL 是否是有效的 RSS/Atom feed"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get('Content-Type', '')
        # 快速判断 Content-Type
        if any(x in ct for x in ['rss', 'atom', 'xml', 'feed']):
            feed = feedparser.parse(r.content)
            return len(feed.entries) > 0
        # 也尝试解析内容（有些网站 Content-Type 不标准）
        if '<rss' in r.text[:500] or '<feed' in r.text[:500]:
            feed = feedparser.parse(r.content)
            return len(feed.entries) > 0
    except Exception:
        pass
    return False


def detect_rss_from_html(root_url, timeout=4):
    """从网站首页 HTML 的 <link> 标签中发现 RSS"""
    try:
        r = requests.get(root_url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        if r.status_code != 200:
            return None
        # 查找 <link rel="alternate" type="application/rss+xml">
        import re
        pattern = r'<link[^>]+(?:application/rss\+xml|application/atom\+xml)[^>]+href=["\']([^"\']+)["\']'
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        if not matches:
            # 也试试反向属性顺序
            pattern2 = r'<link[^>]+href=["\']([^"\']+)["\'][^>]+(?:application/rss\+xml|application/atom\+xml)'
            matches = re.findall(pattern2, r.text, re.IGNORECASE)
        if matches:
            feed_url = matches[0]
            if not feed_url.startswith('http'):
                feed_url = urljoin(root_url, feed_url)
            return feed_url
    except Exception:
        pass
    return None


def check_site(domain, root_url, title):
    """综合检测一个网站的 RSS"""
    # 方法1：从首页 HTML 发现
    feed_url = detect_rss_from_html(root_url)
    if feed_url and is_valid_feed(feed_url):
        return domain, title, feed_url, 'html_autodiscover'

    # 方法2：尝试常见路径
    for path in RSS_PATHS:
        candidate = urljoin(root_url, path)
        if is_valid_feed(candidate):
            return domain, title, candidate, 'common_path'

    return domain, title, None, 'not_found'


# ── 3. 主流程 ────────────────────────────────────────────────────

def main():
    bookmark_file = r'C:\Users\PC\Desktop\网站.html'
    sites = extract_sites(bookmark_file)
    # 只取前10个
    sites = dict(list(sites.items())[:10])
    print(f"共发现 {len(sites)} 个独立域名，开始检测 RSS...\n")

    has_rss = []
    no_rss = []

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(check_site, domain, url, title): domain
            for domain, (url, title) in sites.items()
        }
        done = 0
        for future in as_completed(futures):
            done += 1
            domain, title, feed_url, method = future.result()
            status = '✓' if feed_url else '✗'
            print(f"[{done:>3}/{len(sites)}] {status} {domain}")
            if feed_url:
                has_rss.append((domain, title, feed_url, method))
            else:
                no_rss.append((domain, title))

    # ── 输出结果 ──
    print('\n' + '='*70)
    print(f'有 RSS 的网站 ({len(has_rss)} 个):')
    print('='*70)
    for domain, title, feed_url, method in sorted(has_rss):
        print(f'  {title[:45]:<45} {feed_url}')

    print('\n' + '='*70)
    print(f'无 RSS 的网站 ({len(no_rss)} 个) — 需要爬虫:')
    print('='*70)
    for domain, title in sorted(no_rss):
        print(f'  {title[:45]:<45} https://{domain}/')

    # 保存结果到文件
    with open('rss_check_result.txt', 'w', encoding='utf-8') as f:
        f.write(f'RSS 检测结果\n{"="*70}\n\n')
        f.write(f'有 RSS ({len(has_rss)} 个):\n')
        for domain, title, feed_url, method in sorted(has_rss):
            f.write(f'  {title[:45]:<45} {feed_url}\n')
        f.write(f'\n无 RSS ({len(no_rss)} 个):\n')
        for domain, title in sorted(no_rss):
            f.write(f'  {title[:45]:<45} https://{domain}/\n')

    print(f'\n结果已保存到 rss_check_result.txt')


if __name__ == '__main__':
    main()
