"""
抓取引擎：RSS + HTML 内容抓取
"""
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

import feedparser
from bs4 import BeautifulSoup
from scrapling import Fetcher, DynamicFetcher, StealthyFetcher

DATE_PATTERN = re.compile(r'\d{4}[-/_]\d{2}')
ARTICLE_PATTERN = re.compile(r'/article/')
CONTENT_SELECTORS = (
    'article',
    '[role="main"]',
    '.article-content',
    '.article-content *',
    '.content',
    '.content *',
    '.post-content',
    '.post-content *',
    '.entry-content',
    '.entry-content *',
    '.article-body',
    '.article-body *',
    '.article-detail',
    '.article-detail *',
    '.rich_media_content',
    '.rich_media_content *',
    '.article_main',
    '.article_main *',
    '.main-content',
    '.main-content *',
)

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


def _clean_text(text: str) -> str:
    return re.sub(r'\s+', ' ', (text or '').strip())


def _normalize_url(url: str) -> str:
    raw = (url or '').strip()
    if not raw:
        return ''
    raw, _fragment = urldefrag(raw)
    parsed = urlparse(raw)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    path = parsed.path or ''
    if path != '/':
        path = path.rstrip('/')
    return urlunparse((scheme, netloc, path, '', parsed.query, ''))


def _extract_raw_html_content(page, content_selector: str | list[str] | None) -> str:
    if not content_selector:
        return ''

    selectors = (
        [content_selector]
        if isinstance(content_selector, str)
        else [item for item in content_selector if isinstance(item, str) and item.strip()]
    )
    if not selectors:
        return ''

    raw_body = getattr(page, 'body', '') or ''
    if isinstance(raw_body, bytes):
        raw_body = raw_body.decode('utf-8', errors='ignore')
    if not isinstance(raw_body, str) or not raw_body.strip():
        return ''

    try:
        soup = BeautifulSoup(raw_body, 'html.parser')
    except Exception:
        return ''

    for selector in selectors:
        try:
            elements = soup.select(selector)
        except Exception:
            continue
        chunks = []
        for element in elements:
            text = _clean_text(element.get_text(' ', strip=True))
            if len(text) >= 80:
                chunks.append(text)
        if chunks:
            return '\n\n'.join(chunks)
    return ''


def _extract_page_content(page, content_selector: str | list[str] | None = None) -> str:
    content, _selector_hit = _extract_page_content_with_match(
        page,
        content_selector,
    )
    return content


def _extract_page_content_with_match(
    page,
    content_selector: str | list[str] | None = None,
) -> tuple[str, bool]:
    """返回正文和是否命中指定 content_selector。"""
    raw_content = _extract_raw_html_content(page, content_selector)
    if raw_content:
        return raw_content, True

    text_chunks: list[str] = []
    seen: set[str] = set()

    for selector in CONTENT_SELECTORS:
        try:
            elements = page.css(selector)
        except Exception:
            continue
        for el in elements or []:
            try:
                text = _clean_text(el.text or '')
            except Exception:
                continue
            if len(text) < 80:
                continue
            if text in seen:
                continue
            seen.add(text)
            text_chunks.append(text)
        if text_chunks:
            break

    if text_chunks:
        return '\n\n'.join(text_chunks), False

    try:
        body = page.css('body')
        if body:
            text = _clean_text(body[0].text or '')
            return text, False
    except Exception:
        pass

    return '', False


def _crawl_article_content(
    url: str,
    fetcher='html',
    content_selector: str | list[str] | None = None,
) -> tuple[str, str]:
    if not (url or '').startswith(('http://', 'https://')):
        return '', ''
    try:
        if fetcher == 'js':
            page = DynamicFetcher.fetch(
                url,
                headless=True, network_idle=True, disable_resources=True, timeout=30000
            )
        elif fetcher == 'stealth':
            page = StealthyFetcher.fetch(
                url,
                headless=True, network_idle=True, disable_resources=True, timeout=30000
            )
        else:
            page = Fetcher.get(url, timeout=15)
    except Exception:
        return '', ''

    content = _extract_page_content(page, content_selector)
    if not content:
        content = _clean_text(page.text or '') if getattr(page, 'text', None) else ''
    return content, getattr(page, 'body', '') if hasattr(page, 'body') else ''


def _crawl_article_content_with_match(
    url: str,
    fetcher='html',
    content_selector: str | list[str] | None = None,
) -> tuple[str, bool]:
    """详情页抓取预览专用：返回正文和指定选择器是否命中。"""
    if not (url or '').startswith(('http://', 'https://')):
        return '', False
    try:
        if fetcher == 'js':
            page = DynamicFetcher.fetch(
                url,
                headless=True, network_idle=True, disable_resources=True, timeout=30000
            )
        elif fetcher == 'stealth':
            page = StealthyFetcher.fetch(
                url,
                headless=True, network_idle=True, disable_resources=True, timeout=30000
            )
        else:
            page = Fetcher.get(url, timeout=15)
    except Exception:
        return '', False

    content, selector_hit = _extract_page_content_with_match(
        page,
        content_selector,
    )
    if not content:
        content = _clean_text(page.text or '') if getattr(page, 'text', None) else ''
    return content, selector_hit


def _resolve_article_crawl_mode(site: dict, listing_method: str | None = None) -> str:
    """解析详情页抓取模式；缺少新字段时保持旧 crawl_mode 行为。"""
    configured = site.get('article_crawl_mode')
    if configured in ('html', 'js', 'stealth'):
        return configured

    listing_mode = site.get('crawl_mode', 'auto')
    if listing_mode in ('html', 'js', 'stealth'):
        return listing_mode
    if listing_method in ('html', 'js', 'stealth'):
        return listing_method
    return 'html'


def _attach_article_content(items: list[dict], site: dict) -> list[dict]:
    if not items:
        return items

    article_fetcher = _resolve_article_crawl_mode(
        site,
        listing_method=site.get('_listing_method'),
    )

    max_article_body_len = site.get('max_article_body_len', 0)
    for item in items:
        if item.get('content'):
            continue
        content, _ = _crawl_article_content(
            item.get('url', ''),
            article_fetcher,
            site.get('content_selector'),
        )
        if max_article_body_len and len(content) > max_article_body_len:
            content = content[:max_article_body_len]
        item['content'] = content
    return items


def _listing_items_for_preview(site: dict, limit: int) -> tuple[list[dict], str]:
    """按站点当前列表配置提取少量文章，供规则预览使用。"""
    if site.get('status') == 'rss':
        items = crawl_rss(site)
        return items[:limit], 'rss'

    mode = site.get('crawl_mode', 'auto')
    if mode in ('js', 'stealth'):
        items = crawl_js(site) if mode == 'js' else crawl_stealth(site)
        return items[:limit], mode

    items = crawl_html(site)
    return items[:limit], 'html'


def preview_site_rules(site: dict, limit: int = 3) -> dict:
    """抓取少量列表文章并报告详情页正文规则命中情况。"""
    limit = min(max(int(limit), 1), 10)
    items, listing_method = _listing_items_for_preview(site, limit)
    article_mode = _resolve_article_crawl_mode(site, listing_method)
    preview_items = []

    for item in items:
        content, selector_hit = _crawl_article_content_with_match(
            item.get('url', ''),
            article_mode,
            site.get('content_selector'),
        )
        preview_items.append({
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'content_length': len(content),
            'content_hit': bool(content),
            'content_selector_hit': selector_hit,
            'article_crawl_mode': article_mode,
            'mode': article_mode,
            'hit': bool(content),
            'selector_hit': selector_hit,
        })

    return {
        'site_id': site.get('id'),
        'site_name': site.get('name', ''),
        'listing_method': listing_method,
        'article_crawl_mode': article_mode,
        'content_selector': site.get('content_selector'),
        'content_selector_generated_by': site.get(
            'content_selector_generated_by'
        ),
        'content_selector_generated_at': site.get(
            'content_selector_generated_at'
        ),
        'count': len(preview_items),
        'items': preview_items,
    }


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
                      'content': '',
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
                      'content': '',
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
            'summary': entry.get('summary', '') or entry.get('description', ''),
            'content': '',
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

    if site.get('status') == 'rss':
        items = crawl_rss(site)
        method = 'rss'
    else:
        if mode == 'auto':
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

    skip_urls = {
        normalized for normalized in
        (_normalize_url(url) for url in site.get('_skip_urls', []))
        if normalized
    }
    if skip_urls:
        items = [
            item for item in items
            if _normalize_url(item.get('url', '')) not in skip_urls
        ]

    if not items:
        return None

    if site.get('fetch_article_content', True):
        article_mode = site.get('crawl_mode', 'auto')
        if article_mode == 'auto':
            article_mode = 'html' if method == 'rss' else method
        items = _attach_article_content(
            items,
            {**site, 'crawl_mode': article_mode, '_listing_method': method},
        )

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
              transform_cb=None,
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

    results = [result for result in results if result.get('count', 0) > 0]

    if transform_cb:
        results = [transform_cb(result) for result in results]

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
