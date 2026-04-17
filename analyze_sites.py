"""
批量分析书签网站：RSS检测 + 爬虫可行性分析
超时6秒直接pass
"""
import sys
import re
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
TIMEOUT = 6

RSS_PATHS = ['feed', 'feed/', 'rss', 'rss/', 'rss.xml', 'feed.xml', 'atom.xml', 'index.xml']


def check_rss(root_url):
    """检测是否有RSS，返回feed_url或None"""
    # 方法1：HTML autodiscover
    try:
        r = requests.get(root_url, headers=HEADERS, timeout=TIMEOUT)
        pattern = r'<link[^>]+(?:application/rss\+xml|application/atom\+xml)[^>]+href=["\']([^"\']+)["\']'
        matches = re.findall(pattern, r.text, re.IGNORECASE)
        if not matches:
            pattern2 = r'<link[^>]+href=["\']([^"\']+)["\'][^>]+(?:application/rss\+xml|application/atom\+xml)'
            matches = re.findall(pattern2, r.text, re.IGNORECASE)
        if matches:
            feed_url = matches[0]
            if not feed_url.startswith('http'):
                feed_url = urljoin(root_url, feed_url)
            feed = feedparser.parse(requests.get(feed_url, headers=HEADERS, timeout=TIMEOUT).content)
            if len(feed.entries) > 0:
                return feed_url, 'autodiscover'
    except Exception:
        pass

    # 方法2：常见路径
    for path in RSS_PATHS:
        try:
            url = urljoin(root_url, path)
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            feed = feedparser.parse(r.content)
            if len(feed.entries) > 0:
                return url, 'common_path'
        except Exception:
            pass

    return None, None


def analyze_crawler(root_url):
    """分析爬虫可行性，返回方案描述"""
    try:
        r = requests.get(root_url, headers=HEADERS, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, 'html.parser')

        # 统计有效新闻链接数
        news_links = []
        for a in soup.find_all('a', href=True):
            t = a.get_text(strip=True)
            h = a['href']
            if not h.startswith('http'):
                h = urljoin(root_url, h)
            if 8 <= len(t) <= 80 and re.search(r'\d{4}[-/_]\d{2}', h):
                news_links.append((t, h))

        # 判断是否JS渲染（链接数极少但页面有内容）
        page_text_len = len(soup.get_text(strip=True))
        is_js = len(news_links) == 0 and page_text_len > 500

        if len(news_links) >= 5:
            return 'bs4', len(news_links), news_links[0][1]
        elif is_js:
            return 'js_render', 0, ''
        elif len(news_links) > 0:
            return 'bs4_few', len(news_links), news_links[0][1]
        else:
            return 'unknown', 0, ''
    except requests.Timeout:
        return 'timeout', 0, ''
    except Exception as e:
        return 'error', 0, str(e)


def analyze_site(domain, root_url, title):
    # 先查RSS
    feed_url, method = check_rss(root_url)
    if feed_url:
        return {
            'domain': domain, 'title': title, 'url': root_url,
            'type': 'rss', 'feed_url': feed_url, 'rss_method': method,
            'crawler': None, 'note': ''
        }

    # 无RSS，分析爬虫
    crawler_type, link_count, sample = analyze_crawler(root_url)
    return {
        'domain': domain, 'title': title, 'url': root_url,
        'type': 'crawler' if crawler_type not in ('timeout', 'error') else crawler_type,
        'feed_url': None, 'rss_method': None,
        'crawler': crawler_type, 'link_count': link_count, 'sample': sample, 'note': ''
    }


# ── 主流程 ──
sys.path.insert(0, r'D:\project\PROJECTALL\openmonitor')
from check_rss import extract_sites

sites = extract_sites(r'C:\Users\PC\Desktop\网站.html')
print(f'共 {len(sites)} 个域名，开始分析（超时6秒跳过）...\n')

results = []
with ThreadPoolExecutor(max_workers=15) as executor:
    futures = {
        executor.submit(analyze_site, domain, url, title): domain
        for domain, (url, title) in sites.items()
    }
    done = 0
    for future in as_completed(futures):
        done += 1
        res = future.result()
        results.append(res)
        t = res['type']
        c = res.get('crawler', '')
        print(f"[{done:>3}/{len(sites)}] [{t:<8}] {res['domain']}")

# ── 输出报告 ──
rss_sites     = [r for r in results if r['type'] == 'rss']
bs4_sites     = [r for r in results if r.get('crawler') in ('bs4', 'bs4_few')]
js_sites      = [r for r in results if r.get('crawler') == 'js_render']
timeout_sites = [r for r in results if r['type'] == 'timeout']
error_sites   = [r for r in results if r['type'] == 'error']

report_lines = []
report_lines.append('=' * 70)
report_lines.append(f'爬虫分析报告  共{len(sites)}个网站')
report_lines.append('=' * 70)

report_lines.append(f'\n[1] 有RSS ({len(rss_sites)}个) — 直接订阅')
report_lines.append('-' * 70)
for r in sorted(rss_sites, key=lambda x: x['domain']):
    report_lines.append(f"  {r['title'][:40]:<40} {r['feed_url']}")

report_lines.append(f'\n[2] 静态HTML可爬 ({len(bs4_sites)}个) — BeautifulSoup')
report_lines.append('-' * 70)
for r in sorted(bs4_sites, key=lambda x: x['domain']):
    report_lines.append(f"  {r['title'][:40]:<40} 链接数:{r.get('link_count',0):>3}  {r['url']}")

report_lines.append(f'\n[3] JS渲染 ({len(js_sites)}个) — 需要Playwright')
report_lines.append('-' * 70)
for r in sorted(js_sites, key=lambda x: x['domain']):
    report_lines.append(f"  {r['title'][:40]:<40} {r['url']}")

report_lines.append(f'\n[4] 超时/无响应 ({len(timeout_sites)}个) — 跳过')
report_lines.append('-' * 70)
for r in sorted(timeout_sites, key=lambda x: x['domain']):
    report_lines.append(f"  {r['title'][:40]:<40} {r['url']}")

report_lines.append(f'\n[5] 访问出错 ({len(error_sites)}个)')
report_lines.append('-' * 70)
for r in sorted(error_sites, key=lambda x: x['domain']):
    report_lines.append(f"  {r['title'][:40]:<40} {r['url']}")

report = '\n'.join(report_lines)
print('\n' + report)

with open('site_analysis_report.txt', 'w', encoding='utf-8') as f:
    f.write(report)
print('\n报告已保存到 site_analysis_report.txt')
