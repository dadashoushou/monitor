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
from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

DATE_PATTERN = re.compile(r'\d{4}[-/_]\d{2}')


def _extract_articles(page, site_url: str) -> list[dict]:
    """从 Scrapling Response 中提取文章链接列表，最多 30 条。
    筛选规则：标题 8-80 字符，href 含日期模式 (YYYY-MM 或 YYYY/MM)。
    """
    items = []
    for el in page.css('a[href]'):
        text = el.text.strip() if el.text else ''
        href = el.attrib.get('href', '')
        if not (8 <= len(text) <= 80):
            continue
        if not DATE_PATTERN.search(href):
            continue
        if not href.startswith('http'):
            href = urljoin(site_url, href)
        items.append({'title': text, 'url': href, 'published': ''})
        if len(items) >= 30:
            break
    return items


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
    """用 Scrapling Fetcher 抓取首页，提取文章链接"""
    try:
        page = Fetcher().get(site['url'], stealthy_headers=True, timeout=10)
    except Exception:
        return []
    return _extract_articles(page, site['url'])


def crawl_js(site: dict) -> list[dict]:
    """用 Scrapling DynamicFetcher 抓取 JS 渲染页面"""
    try:
        page = DynamicFetcher().fetch(
            site['url'],
            headless=True, network_idle=True, disable_resources=True, timeout=30000
        )
    except Exception:
        return []
    return _extract_articles(page, site['url'])


def crawl_stealth(site: dict) -> list[dict]:
    """用 Scrapling StealthyFetcher 抓取有 bot 防护的页面"""
    try:
        page = StealthyFetcher().fetch(
            site['url'],
            headless=True, network_idle=True, disable_resources=True, timeout=30000
        )
    except Exception:
        return []
    return _extract_articles(page, site['url'])


def crawl_site(site: dict) -> dict | None:
    """抓取单个网站，返回结果 dict，无结果返回 None"""
    if site.get('status') == 'rss':
        items = crawl_rss(site)
        method = 'rss'
    else:
        items = crawl_html(site)
        method = 'html'

    if not items:
        return None

    return {
        'site_id': site['id'],
        'site_name': site['name'],
        'site_url': site['url'],
        'method': method,
        'count': len(items),
        'items': items,
    }


def crawl_all(sites: list[dict], data_dir: Path) -> list[dict]:
    """并发抓取所有网站，将所有结果合并写入一个 JSON 文件，返回有结果的列表"""
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(crawl_site, site): site for site in sites}
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception:
                pass

    if results:
        data_dir.mkdir(parents=True, exist_ok=True)
        crawled_at = datetime.now().isoformat(timespec='seconds')
        ts = crawled_at.replace(':', '-').replace('T', '_')
        filename = f"{ts}_all.json"
        merged = {
            'crawled_at': crawled_at,
            'count': len(results),
            'sites': results,
        }
        with open(data_dir / filename, 'w', encoding='utf-8') as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

    return results
