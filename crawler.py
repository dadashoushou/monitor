"""
抓取引擎：RSS + HTML 内容抓取
"""
import re
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / 'data'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; openmonitor-crawler/1.0)'}
DATE_PATTERN = re.compile(r'\d{4}[-/_]\d{2}')


def _parsed_time_to_iso(t) -> str:
    """将 feedparser 的 time.struct_time 转为 ISO 字符串，失败返回空字符串"""
    if not t:
        return ''
    try:
        return datetime(*t[:6]).isoformat(timespec='seconds')
    except Exception:
        return ''


def crawl_rss(site: dict) -> list[dict]:
    """用 feedparser 抓取 site['rss_url']，返回条目列表"""
    feed = feedparser.parse(site['rss_url'])
    items = []
    for entry in feed.entries:
        published = _parsed_time_to_iso(
            getattr(entry, 'published_parsed', None) or
            getattr(entry, 'updated_parsed', None)
        )
        items.append({
            'title': entry.get('title', ''),
            'url': entry.get('link', ''),
            'published': published,
        })
    return items


def crawl_html(site: dict) -> list[dict]:
    """用 requests+BeautifulSoup 抓取首页，提取文章链接，最多 30 条"""
    try:
        r = requests.get(site['url'], headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(r.text, 'html.parser')
    items = []

    for a in soup.find_all('a', href=True):
        text = a.get_text(strip=True)
        href = a['href']
        if not (8 <= len(text) <= 80):
            continue
        if not DATE_PATTERN.search(href):
            continue

        if not href.startswith('http'):
            href = urljoin(site['url'], href)

        published = ''
        parent = a.parent
        if parent:
            time_tag = parent.find('time')
            if time_tag:
                published = time_tag.get('datetime', time_tag.get_text(strip=True))
            else:
                for sibling in list(parent.children):
                    sib_text = getattr(sibling, 'get_text', lambda **kw: str(sibling))(strip=True)
                    if DATE_PATTERN.search(sib_text):
                        published = sib_text
                        break

        items.append({'title': text, 'url': href, 'published': published})
        if len(items) >= 30:
            break

    return items


def crawl_site(site: dict) -> dict | None:
    """抓取单个网站，有结果则写文件并返回 dict，否则返回 None"""
    if site.get('status') == 'rss':
        items = crawl_rss(site)
        method = 'rss'
    else:
        items = crawl_html(site)
        method = 'html'

    if not items:
        return None

    DATA_DIR.mkdir(exist_ok=True)
    crawled_at = datetime.now().isoformat(timespec='seconds')
    ts = crawled_at.replace(':', '-').replace('T', '_')
    filename = f"{ts}_{site['id']}.json"

    result = {
        'site_id': site['id'],
        'site_name': site['name'],
        'site_url': site['url'],
        'crawled_at': crawled_at,
        'method': method,
        'count': len(items),
        'items': items,
    }

    with open(DATA_DIR / filename, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def crawl_all(sites: list[dict]) -> list[dict]:
    """并发抓取所有网站，返回有结果的列表"""
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(crawl_site, site): site for site in sites}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)
    return results
