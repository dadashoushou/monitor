import re
from unittest.mock import MagicMock, patch
from urllib.parse import urljoin

DATE_PATTERN = re.compile(r'\d{4}[-/_]\d{2}')


def _make_mock_element(text, href, attrib=None):
    """构造模拟的 Scrapling element"""
    el = MagicMock()
    el.text = text
    el.attrib = attrib or {'href': href}
    return el


def test_extract_articles_basic():
    """基本提取：标题长度 8-80，href 含日期模式"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('这是一篇测试文章标题足够长', '/2024/03/article-1', {'href': '/2024/03/article-1'}),
        _make_mock_element('短', '/2024/03/short', {'href': '/2024/03/short'}),
        _make_mock_element('这是另一篇有效的文章标题哦', '/news/no-date-here', {'href': '/news/no-date-here'}),
    ]

    items = _extract_articles(mock_page, 'https://example.com')
    assert len(items) == 1
    assert items[0]['title'] == '这是一篇测试文章标题足够长'
    assert items[0]['url'] == 'https://example.com/2024/03/article-1'


def test_extract_articles_max_items():
    """默认最多返回 200 条，可通过 max_items 参数控制"""
    from crawler import _extract_articles

    elements = [
        _make_mock_element(f'有效文章标题编号{i:03d}很长', f'/2024/01/art-{i}', {'href': f'/2024/01/art-{i}'})
        for i in range(250)
    ]
    mock_page = MagicMock()
    mock_page.css.return_value = elements

    items = _extract_articles(mock_page, 'https://example.com')
    assert len(items) == 200

    items_50 = _extract_articles(mock_page, 'https://example.com', max_items=50)
    assert len(items_50) == 50


def test_extract_articles_absolute_url():
    """已有 http 前缀的 href 不做拼接"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('绝对路径的文章标题足够长', 'https://other.com/2024/05/post',
                           {'href': 'https://other.com/2024/05/post'}),
    ]

    items = _extract_articles(mock_page, 'https://example.com')
    assert items[0]['url'] == 'https://other.com/2024/05/post'


def test_extract_articles_article_path():
    """href 含 /article/ 路径也能匹配（如网易新闻）"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('网易新闻的文章标题足够长', '/dy/article/KQLEUTTL000181BR.html',
                           {'href': '/dy/article/KQLEUTTL000181BR.html'}),
        _make_mock_element('无日期也无article的链接', '/some/random/path',
                           {'href': '/some/random/path'}),
    ]

    items = _extract_articles(mock_page, 'https://www.163.com')
    assert len(items) == 1
    assert items[0]['url'] == 'https://www.163.com/dy/article/KQLEUTTL000181BR.html'


def test_crawl_html_calls_fetcher_and_extract():
    """crawl_html 应使用 Fetcher.get 并调用 _extract_articles"""
    from crawler import crawl_html

    site = {'url': 'https://example.com', 'id': '123', 'name': 'Test'}
    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('有效文章标题长度足够了', '/2024/06/post-1', {'href': '/2024/06/post-1'}),
    ]

    with patch('crawler.Fetcher') as MockFetcher:
        MockFetcher.get.return_value = mock_page
        items = crawl_html(site)

    MockFetcher.get.assert_called_once_with(
        'https://example.com', timeout=10
    )
    assert len(items) == 1
    assert items[0]['title'] == '有效文章标题长度足够了'


def test_crawl_html_returns_empty_on_exception():
    """Fetcher 抛异常时返回空列表"""
    from crawler import crawl_html

    site = {'url': 'https://example.com', 'id': '123', 'name': 'Test'}

    with patch('crawler.Fetcher') as MockFetcher:
        MockFetcher.get.side_effect = Exception('network error')
        items = crawl_html(site)

    assert items == []


def test_crawl_js_calls_dynamic_fetcher():
    """crawl_js 应使用 DynamicFetcher.fetch"""
    from crawler import crawl_js

    site = {'url': 'https://spa-site.com', 'id': '456', 'name': 'SPA'}
    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('动态渲染的文章标题够长', '/2024/07/js-post', {'href': '/2024/07/js-post'}),
    ]

    with patch('crawler.DynamicFetcher') as MockDF:
        MockDF.fetch.return_value = mock_page
        items = crawl_js(site)

    MockDF.fetch.assert_called_once_with(
        'https://spa-site.com',
        headless=True, network_idle=True, disable_resources=True, timeout=30000
    )
    assert len(items) == 1


def test_crawl_js_returns_empty_on_exception():
    from crawler import crawl_js

    site = {'url': 'https://spa-site.com', 'id': '456', 'name': 'SPA'}
    with patch('crawler.DynamicFetcher') as MockDF:
        MockDF.fetch.side_effect = Exception('browser crash')
        items = crawl_js(site)
    assert items == []


def test_crawl_stealth_calls_stealthy_fetcher():
    """crawl_stealth 应使用 StealthyFetcher.fetch"""
    from crawler import crawl_stealth

    site = {'url': 'https://protected.com', 'id': '789', 'name': 'Protected'}
    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('隐蔽抓取的文章标题够长', '/2024/08/stealth', {'href': '/2024/08/stealth'}),
    ]

    with patch('crawler.StealthyFetcher') as MockSF:
        MockSF.fetch.return_value = mock_page
        items = crawl_stealth(site)

    MockSF.fetch.assert_called_once_with(
        'https://protected.com',
        headless=True, network_idle=True, disable_resources=True, timeout=30000
    )
    assert len(items) == 1


def test_crawl_stealth_returns_empty_on_exception():
    from crawler import crawl_stealth

    site = {'url': 'https://protected.com', 'id': '789', 'name': 'Protected'}
    with patch('crawler.StealthyFetcher') as MockSF:
        MockSF.fetch.side_effect = Exception('blocked')
        items = crawl_stealth(site)
    assert items == []


def test_crawl_site_auto_rss():
    """auto 模式 + status=rss → 走 crawl_rss"""
    from crawler import crawl_site

    site = {'id': '1', 'name': 'RSS站点', 'url': 'https://rss.com',
            'rss_url': 'https://rss.com/feed', 'status': 'rss', 'crawl_mode': 'auto'}

    with patch('crawler.crawl_rss', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_rss:
        result = crawl_site(site)

    mock_rss.assert_called_once_with(site)
    assert result['method'] == 'rss'
    assert result['count'] == 1


def test_crawl_site_auto_no_rss():
    """auto 模式 + status!=rss → 走 crawl_html"""
    from crawler import crawl_site

    site = {'id': '2', 'name': 'HTML站点', 'url': 'https://html.com',
            'status': 'no_rss', 'crawl_mode': 'auto'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_html:
        result = crawl_site(site)

    mock_html.assert_called_once_with(site)
    assert result['method'] == 'html'


def test_crawl_site_js_mode():
    """js 模式 → 走 crawl_js"""
    from crawler import crawl_site

    site = {'id': '3', 'name': 'SPA站点', 'url': 'https://spa.com',
            'status': 'no_rss', 'crawl_mode': 'js'}

    with patch('crawler.crawl_js', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_js:
        result = crawl_site(site)

    mock_js.assert_called_once_with(site)
    assert result['method'] == 'js'


def test_crawl_site_stealth_mode():
    """stealth 模式 → 走 crawl_stealth"""
    from crawler import crawl_site

    site = {'id': '4', 'name': '防护站点', 'url': 'https://cf.com',
            'status': 'no_rss', 'crawl_mode': 'stealth'}

    with patch('crawler.crawl_stealth', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_st:
        result = crawl_site(site)

    mock_st.assert_called_once_with(site)
    assert result['method'] == 'stealth'


def test_crawl_site_html_mode():
    """html 模式 → 强制走 crawl_html，即使有 RSS"""
    from crawler import crawl_site

    site = {'id': '5', 'name': 'Force HTML', 'url': 'https://force.com',
            'rss_url': 'https://force.com/feed', 'status': 'rss', 'crawl_mode': 'html'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_html:
        result = crawl_site(site)

    mock_html.assert_called_once_with(site)
    assert result['method'] == 'html'


def test_crawl_site_no_crawl_mode_defaults_auto():
    """无 crawl_mode 字段 → 默认 auto"""
    from crawler import crawl_site

    site = {'id': '6', 'name': 'Old', 'url': 'https://old.com', 'status': 'no_rss'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_html:
        result = crawl_site(site)

    mock_html.assert_called_once_with(site)
    assert result['method'] == 'html'


def test_crawl_site_returns_none_on_empty():
    """抓取结果为空 → 返回 None"""
    from crawler import crawl_site

    site = {'id': '7', 'name': 'Empty', 'url': 'https://empty.com', 'status': 'no_rss'}

    with patch('crawler.crawl_html', return_value=[]):
        result = crawl_site(site)

    assert result is None


def test_crawl_all_splits_by_mode(tmp_path):
    """crawl_all 应将站点按模式分组并发"""
    from crawler import crawl_all

    sites = [
        {'id': '1', 'name': 'A', 'url': 'https://a.com', 'status': 'rss',
         'rss_url': 'https://a.com/feed', 'crawl_mode': 'auto'},
        {'id': '2', 'name': 'B', 'url': 'https://b.com', 'status': 'no_rss',
         'crawl_mode': 'js'},
    ]

    fake_result = lambda site: {
        'site_id': site['id'], 'site_name': site['name'],
        'site_url': site['url'], 'method': 'mock',
        'count': 1, 'items': [{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}],
    }

    with patch('crawler.crawl_site', side_effect=fake_result):
        results = crawl_all(sites, tmp_path)

    assert len(results) == 2
    json_files = list(tmp_path.glob('*.json'))
    assert len(json_files) == 1


def test_crawl_all_empty_sites(tmp_path):
    """空站点列表 → 返回空，不写文件"""
    from crawler import crawl_all

    results = crawl_all([], tmp_path)
    assert results == []
    assert list(tmp_path.glob('*.json')) == []


def test_extract_articles_with_css_selector():
    """selectors 路径：用 css_selector 提取文章"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('AI生成规则提取的文章标题', '/news/12345.html', {'href': '/news/12345.html'}),
        _make_mock_element('第二篇文章标题也足够长', '/news/67890.html', {'href': '/news/67890.html'}),
    ]

    selectors = {'css_selector': 'a.news-link', 'min_title_len': 8, 'max_title_len': 80}
    items = _extract_articles(mock_page, 'https://example.com', selectors)
    assert len(items) == 2
    assert items[0]['title'] == 'AI生成规则提取的文章标题'
    mock_page.css.assert_called_with('a.news-link')


def test_extract_articles_with_url_pattern():
    """selectors 路径：url_pattern 过滤非文章链接"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('匹配URL模式的文章标题', '/article/12345.html', {'href': '/article/12345.html'}),
        _make_mock_element('不匹配URL模式的链接标题', '/about/contact.html', {'href': '/about/contact.html'}),
    ]

    selectors = {'css_selector': 'a', 'url_pattern': r'/article/', 'min_title_len': 8, 'max_title_len': 80}
    items = _extract_articles(mock_page, 'https://example.com', selectors)
    assert len(items) == 1
    assert items[0]['url'] == 'https://example.com/article/12345.html'


def test_extract_articles_time_url():
    """selectors 路径：从 URL 提取发布时间"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('含日期URL的文章标题足够长', '/2026/04/17/news.html', {'href': '/2026/04/17/news.html'}),
    ]

    selectors = {
        'css_selector': 'a',
        'time_source': 'time_url',
        'time_url_pattern': r'/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/',
        'min_title_len': 8,
        'max_title_len': 80,
    }
    items = _extract_articles(mock_page, 'https://example.com', selectors)
    assert len(items) == 1
    assert items[0]['published'] == '2026-04-17'


def test_extract_articles_time_css():
    """selectors 路径：从 HTML 元素提取发布时间"""
    from crawler import _extract_articles

    time_el = MagicMock()
    time_el.text = '2026-04-17 10:00'

    parent = MagicMock()
    parent.css.return_value = [time_el]

    link_el = _make_mock_element('有时间元素的文章标题足够长', '/news/123.html', {'href': '/news/123.html'})
    link_el.parent = parent

    mock_page = MagicMock()
    mock_page.css.return_value = [link_el]

    selectors = {
        'css_selector': 'a',
        'time_source': 'time_css',
        'time_css': 'span.time',
        'min_title_len': 8,
        'max_title_len': 80,
    }
    items = _extract_articles(mock_page, 'https://example.com', selectors)
    assert len(items) == 1
    assert items[0]['published'] == '2026-04-17 10:00'


def test_extract_articles_selectors_fallback():
    """selectors=None 时走旧的硬编码逻辑"""
    from crawler import _extract_articles

    mock_page = MagicMock()
    mock_page.css.return_value = [
        _make_mock_element('硬编码逻辑匹配日期URL的标题', '/2024/03/article-1', {'href': '/2024/03/article-1'}),
    ]

    items = _extract_articles(mock_page, 'https://example.com', None)
    assert len(items) == 1
    assert items[0]['title'] == '硬编码逻辑匹配日期URL的标题'
    mock_page.css.assert_called_with('a[href]')


def test_parse_published_formats():
    """_parse_published 支持多种日期格式"""
    from crawler import _parse_published
    from datetime import datetime

    assert _parse_published('2026-04-17T10:30:00') == datetime(2026, 4, 17, 10, 30, 0)
    assert _parse_published('2026-04-17 10:30') == datetime(2026, 4, 17, 10, 30)
    assert _parse_published('2026-04-17') == datetime(2026, 4, 17)
    assert _parse_published('') is None
    assert _parse_published('invalid') is None


def test_filter_by_age_keeps_recent():
    """_filter_by_age 保留近期条目，过滤过期条目"""
    from crawler import _filter_by_age
    from datetime import datetime, timedelta

    today = datetime.now().strftime('%Y-%m-%d')
    old = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    items = [
        {'title': 'new', 'url': 'http://a.com/1', 'published': today, 'crawled_at': today},
        {'title': 'old', 'url': 'http://a.com/2', 'published': old, 'crawled_at': old},
        {'title': 'no date', 'url': 'http://a.com/3', 'published': None, 'crawled_at': None},
    ]
    result = _filter_by_age(items, 7)
    assert len(result) == 2
    assert result[0]['title'] == 'new'
    assert result[1]['title'] == 'no date'


def test_filter_by_age_zero_disables():
    """max_age_days=0 不过滤"""
    from crawler import _filter_by_age

    items = [{'title': 'a', 'url': 'http://a.com/1', 'published': '2020-01-01', 'crawled_at': '2020-01-01'}]
    result = _filter_by_age(items, 0)
    assert len(result) == 1


def test_filter_by_age_crawled_at_fallback():
    """published=None 时用 crawled_at 做时间过滤"""
    from crawler import _filter_by_age
    from datetime import datetime, timedelta

    today = datetime.now().strftime('%Y-%m-%d')
    old = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')

    items = [
        {'title': 'recent crawl', 'url': 'http://a.com/1', 'published': None, 'crawled_at': today},
        {'title': 'old crawl', 'url': 'http://a.com/2', 'published': None, 'crawled_at': old},
    ]
    result = _filter_by_age(items, 7)
    assert len(result) == 1
    assert result[0]['title'] == 'recent crawl'
