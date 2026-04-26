"""
抓取引擎：RSS + HTML 内容抓取
"""
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import urljoin

import feedparser
from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

DATE_PATTERN = re.compile(r'\d{4}[-/_]\d{2}')
ARTICLE_PATTERN = re.compile(r'/article/')

_PUBLISHED_FORMATS = ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d')


def _parse_published(pub: str) -> datetime | None:
    for fmt in _PUBLISHED_FORMATS:
        try:
            return datetime.strptime(pub, fmt)
        except ValueError:
            continue
    return None


def _filter_by_age(items: list[dict], max_age_days: int) -> list[dict]:
    if max_age_days <= 0:
        return items
    cutoff = datetime.now() - timedelta(days=max_age_days)
    result = []
    for item in items:
        pub = item.get('published') or item.get('crawled_at') or ''
        if not pub:
            result.append(item)
            continue
        dt = _parse_published(pub)
        if dt is None or dt >= cutoff:
            result.append(item)
    return result


def _extract_time_from_url(href: str, pattern: re.Pattern) -> str:
    """用正则从 URL 提取时间，返回 YYYY-MM-DD 或空字符串"""
    m = pattern.search(href)
    if not m:
        return ''
    g = m.groupdict()
    y, mo, d = g.get('year', ''), g.get('month', ''), g.get('day', '')
    if y and mo and d:
        return f'{y}-{mo}-{d}'
    if y and mo:
        return f'{y}-{mo}'
    return ''


def _extract_articles(page, site_url: str, selectors: dict = None,
                      max_items: int = 200) -> list[dict]:
    """从 Scrapling Response 中提取文章链接列表。
    如果提供 selectors 则使用 AI 生成的规则，否则走硬编码逻辑。
    """
    if selectors and selectors.get('css_selector'):
        return _extract_with_selectors(page, site_url, selectors, max_items)

    items = []
    seen_urls: set[str] = set()
    for el in page.css('a[href]'):
        text = el.text.strip() if el.text else ''
        href = el.attrib.get('href', '')
        if not (8 <= len(text) <= 80):
            continue
        if not DATE_PATTERN.search(href) and not ARTICLE_PATTERN.search(href):
            continue
        if not href.startswith('http'):
            href = urljoin(site_url, href)
        if href in seen_urls:
            continue
        seen_urls.add(href)
        items.append({'title': text, 'url': href, 'published': None,
                      'crawled_at': datetime.now().isoformat(timespec='seconds')})
        if len(items) >= max_items:
            break
    return items


def _extract_with_selectors(page, site_url: str, selectors: dict,
                            max_items: int = 200) -> list[dict]:
    """使用 AI 生成的 selectors 规则提取文章列表"""
    css = selectors['css_selector']
    url_pat = re.compile(selectors['url_pattern']) if selectors.get('url_pattern') else None
    title_attr = selectors.get('title_attr')
    min_len = selectors.get('min_title_len', 8)
    max_len = selectors.get('max_title_len', 80)

    time_source = selectors.get('time_source')
    time_url_pat = None
    if time_source == 'time_url' and selectors.get('time_url_pattern'):
        time_url_pat = re.compile(selectors['time_url_pattern'])
    time_css = selectors.get('time_css') if time_source == 'time_css' else None

    items = []
    seen_urls: set[str] = set()
    for el in page.css(css):
        if title_attr:
            text = (el.attrib.get(title_attr, '') or '').strip()
        else:
            text = el.text.strip() if el.text else ''
        href = el.attrib.get('href', '')

        if not (min_len <= len(text) <= max_len):
            continue
        if url_pat and not url_pat.search(href):
            continue
        if not href.startswith('http'):
            href = urljoin(site_url, href)
        if href in seen_urls:
            continue
        seen_urls.add(href)

        published = None
        if time_url_pat:
            published = _extract_time_from_url(href, time_url_pat) or None
        elif time_css:
            try:
                parent = el.parent
                if parent:
                    time_els = parent.css(time_css)
                    if time_els:
                        published = (time_els[0].text or '').strip() or None
            except Exception:
                pass

        items.append({'title': text, 'url': href, 'published': published,
                      'crawled_at': datetime.now().isoformat(timespec='seconds')})
        if len(items) >= max_items:
            break
    return items


def _parsed_time_to_iso(t) -> str:
    """将 feedparser 的 time.struct_time 转为 ISO 字符串，失败返回空字符串"""
    if not t:
        return None
    try:
        return datetime(*t[:6]).isoformat(timespec='seconds')
    except Exception:
        return None


def crawl_rss(site: dict) -> list[dict]:
    """用 feedparser 抓取 site['rss_url']，返回条目列表"""
    feed = feedparser.parse(site['rss_url'])
    items = []
    seen_urls: set[str] = set()
    for entry in feed.entries:
        url = entry.get('link', '')
        if url in seen_urls:
            continue
        seen_urls.add(url)
        published = _parsed_time_to_iso(
            getattr(entry, 'published_parsed', None) or
            getattr(entry, 'updated_parsed', None)
        )
        items.append({
            'title': entry.get('title', ''),
            'url': url,
            'published': published,
            'crawled_at': datetime.now().isoformat(timespec='seconds'),
        })
    return items


def crawl_html(site: dict) -> list[dict]:
    """用 Scrapling Fetcher 抓取首页，提取文章链接"""
    try:
        page = Fetcher.get(site['url'], timeout=10)
    except Exception:
        return []
    max_items = site.get('max_items', 200)
    return _extract_articles(page, site['url'], site.get('selectors'), max_items)


def crawl_js(site: dict) -> list[dict]:
    """用 Scrapling DynamicFetcher 抓取 JS 渲染页面"""
    try:
        page = DynamicFetcher.fetch(
            site['url'],
            headless=True, network_idle=True, disable_resources=True, timeout=30000
        )
    except Exception:
        return []
    max_items = site.get('max_items', 200)
    return _extract_articles(page, site['url'], site.get('selectors'), max_items)


def crawl_stealth(site: dict) -> list[dict]:
    """用 Scrapling StealthyFetcher 抓取有 bot 防护的页面"""
    try:
        page = StealthyFetcher.fetch(
            site['url'],
            headless=True, network_idle=True, disable_resources=True, timeout=30000
        )
    except Exception:
        return []
    max_items = site.get('max_items', 200)
    return _extract_articles(page, site['url'], site.get('selectors'), max_items)


def crawl_site(site: dict) -> dict | None:
    """根据 crawl_mode 路由到对应抓取函数，返回结果 dict 或 None"""
    if site.get('crawl_paused'):
        return None

    mode = site.get('crawl_mode', 'auto')

    if mode == 'auto':
        if site.get('status') == 'rss':
            items = crawl_rss(site)
            method = 'rss'
        else:
            items = crawl_html(site)
            method = 'html'
    elif mode == 'html':
        items = crawl_html(site)
        method = 'html'
    elif mode == 'js':
        items = crawl_js(site)
        method = 'js'
    elif mode == 'stealth':
        items = crawl_stealth(site)
        method = 'stealth'
    else:
        items = crawl_html(site)
        method = 'html'

    if not items:
        return None

    max_age_days = site.get('max_article_age_days', 0)
    if max_age_days > 0:
        items = _filter_by_age(items, max_age_days)

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


def crawl_all(sites: list[dict], data_dir: Path,
              prev_urls_loader=None, dedupe_cb=None, save_hook=None,
              should_stop=None, progress_cb=None) -> list[dict]:
    """按模式分组并发抓取：静态(rss/html/auto) max_workers=5，动态(js/stealth) max_workers=2"""
    static_sites = []
    dynamic_sites = []
    for s in sites:
        if s.get('crawl_paused'):
            continue
        mode = s.get('crawl_mode', 'auto')
        if mode in ('js', 'stealth'):
            dynamic_sites.append(s)
        else:
            static_sites.append(s)

    results = []
    should_stop = should_stop or (lambda: False)

    def _collect(executor_sites, max_workers):
        if not executor_sites:
            return
        site_iter = iter(executor_sites)
        pending = {}
        exhausted = False
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while pending or not exhausted:
                while not exhausted and len(pending) < max_workers and not should_stop():
                    try:
                        site = next(site_iter)
                    except StopIteration:
                        exhausted = True
                        break
                    pending[executor.submit(crawl_site, site)] = site

                if not pending:
                    break

                done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                for future in done:
                    site = pending.pop(future)
                    result = None
                    try:
                        result = future.result()
                        if result is not None:
                            results.append(result)
                    except Exception:
                        pass
                    if progress_cb:
                        progress_cb(site, result)

            for future, site in list(pending.items()):
                result = None
                try:
                    result = future.result()
                    if result is not None:
                        results.append(result)
                except Exception:
                    pass
                if progress_cb:
                    progress_cb(site, result)

    _collect(static_sites, 5)
    if not should_stop():
        _collect(dynamic_sites, 2)

    if dedupe_cb:
        for result in results:
            result['items'] = dedupe_cb(result['site_id'], result['items'])
            result['count'] = len(result['items'])
    elif prev_urls_loader:
        for result in results:
            prev_urls = prev_urls_loader(result['site_id'])
            if prev_urls:
                result['items'] = [i for i in result['items'] if i['url'] not in prev_urls]
                result['count'] = len(result['items'])

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
        if save_hook:
            save_hook(merged, filename)

    return results
