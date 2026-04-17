"""
检测目标网站是否有 RSS
"""
import requests
import feedparser
from urllib.parse import urljoin

SITES = [
    ("人民网",     "http://www.people.com.cn/"),
    ("新华网",     "http://www.xinhuanet.com/"),
    ("央视网",     "http://www.cctv.com/"),
    ("中国新闻网", "http://www.chinanews.com.cn/"),
    ("新浪新闻",   "https://news.sina.com.cn/"),
    ("腾讯新闻",   "https://news.qq.com/"),
    ("网易新闻",   "https://news.163.com/"),
    ("观察者网",   "https://www.guancha.cn/"),
]

RSS_PATHS = [
    'rss', 'rss/', 'rss.xml', 'feed', 'feed/', 'feed.xml',
    'atom.xml', 'index.xml', 'rss/news.xml', 'rss/politics.xml',
]

HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; RSS-checker/1.0)'}

def is_valid_feed(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=5, allow_redirects=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get('Content-Type', '')
        if any(x in ct for x in ['rss', 'atom', 'xml', 'feed']):
            feed = feedparser.parse(r.content)
            return len(feed.entries) > 0
        if '<rss' in r.text[:500] or '<feed' in r.text[:500]:
            feed = feedparser.parse(r.content)
            return len(feed.entries) > 0
    except Exception:
        pass
    return False

def detect_from_html(root_url):
    import re
    try:
        r = requests.get(root_url, headers=HEADERS, timeout=5, allow_redirects=True)
        if r.status_code != 200:
            return None
        pattern = r'<link[^>]+(?:application/rss\+xml|application/atom\+xml)[^>]+href=["\']([^"\']+)["\']'
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        if not matches:
            pattern2 = r'<link[^>]+href=["\']([^"\']+)["\'][^>]+(?:application/rss\+xml|application/atom\+xml)'
            matches = re.findall(pattern2, r.text, re.IGNORECASE)
        if matches:
            url = matches[0]
            if not url.startswith('http'):
                url = urljoin(root_url, url)
            return url
    except Exception:
        pass
    return None

for name, root in SITES:
    print(f"\n检测 {name} ({root})")

    # 方法1：HTML autodiscover
    feed_url = detect_from_html(root)
    if feed_url and is_valid_feed(feed_url):
        print(f"  [OK] RSS (autodiscover): {feed_url}")
        continue

    # 方法2：常见路径
    found = False
    for path in RSS_PATHS:
        candidate = urljoin(root, path)
        if is_valid_feed(candidate):
            print(f"  [OK] RSS (common path): {candidate}")
            found = True
            break

    if not found:
        print(f"  [NO] no RSS, need crawler")
