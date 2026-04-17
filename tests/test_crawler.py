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


def test_extract_articles_max_30():
    """最多返回 30 条"""
    from crawler import _extract_articles

    elements = [
        _make_mock_element(f'有效文章标题编号{i:03d}很长', f'/2024/01/art-{i}', {'href': f'/2024/01/art-{i}'})
        for i in range(50)
    ]
    mock_page = MagicMock()
    mock_page.css.return_value = elements

    items = _extract_articles(mock_page, 'https://example.com')
    assert len(items) == 30


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
        MockFetcher.return_value.get.return_value = mock_page
        items = crawl_html(site)

    MockFetcher.return_value.get.assert_called_once_with(
        'https://example.com', stealthy_headers=True, timeout=10
    )
    assert len(items) == 1
    assert items[0]['title'] == '有效文章标题长度足够了'


def test_crawl_html_returns_empty_on_exception():
    """Fetcher 抛异常时返回空列表"""
    from crawler import crawl_html

    site = {'url': 'https://example.com', 'id': '123', 'name': 'Test'}

    with patch('crawler.Fetcher') as MockFetcher:
        MockFetcher.return_value.get.side_effect = Exception('network error')
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
        MockDF.return_value.fetch.return_value = mock_page
        items = crawl_js(site)

    MockDF.return_value.fetch.assert_called_once_with(
        'https://spa-site.com',
        headless=True, network_idle=True, disable_resources=True, timeout=30000
    )
    assert len(items) == 1


def test_crawl_js_returns_empty_on_exception():
    from crawler import crawl_js

    site = {'url': 'https://spa-site.com', 'id': '456', 'name': 'SPA'}
    with patch('crawler.DynamicFetcher') as MockDF:
        MockDF.return_value.fetch.side_effect = Exception('browser crash')
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
        MockSF.return_value.fetch.return_value = mock_page
        items = crawl_stealth(site)

    MockSF.return_value.fetch.assert_called_once_with(
        'https://protected.com',
        headless=True, network_idle=True, disable_resources=True, timeout=30000
    )
    assert len(items) == 1


def test_crawl_stealth_returns_empty_on_exception():
    from crawler import crawl_stealth

    site = {'url': 'https://protected.com', 'id': '789', 'name': 'Protected'}
    with patch('crawler.StealthyFetcher') as MockSF:
        MockSF.return_value.fetch.side_effect = Exception('blocked')
        items = crawl_stealth(site)
    assert items == []


def test_crawl_site_auto_rss():
    """auto 模式 + status=rss → 走 crawl_rss"""
    from crawler import crawl_site

    site = {'id': '1', 'name': 'RSS站点', 'url': 'https://rss.com',
            'rss_url': 'https://rss.com/feed', 'status': 'rss', 'crawl_mode': 'auto'}

    with patch('crawler.crawl_rss', return_value=[{'title': 'T', 'url': 'U', 'published': ''}]) as mock_rss:
        result = crawl_site(site)

    mock_rss.assert_called_once_with(site)
    assert result['method'] == 'rss'
    assert result['count'] == 1


def test_crawl_site_auto_no_rss():
    """auto 模式 + status!=rss → 走 crawl_html"""
    from crawler import crawl_site

    site = {'id': '2', 'name': 'HTML站点', 'url': 'https://html.com',
            'status': 'no_rss', 'crawl_mode': 'auto'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': ''}]) as mock_html:
        result = crawl_site(site)

    mock_html.assert_called_once_with(site)
    assert result['method'] == 'html'


def test_crawl_site_js_mode():
    """js 模式 → 走 crawl_js"""
    from crawler import crawl_site

    site = {'id': '3', 'name': 'SPA站点', 'url': 'https://spa.com',
            'status': 'no_rss', 'crawl_mode': 'js'}

    with patch('crawler.crawl_js', return_value=[{'title': 'T', 'url': 'U', 'published': ''}]) as mock_js:
        result = crawl_site(site)

    mock_js.assert_called_once_with(site)
    assert result['method'] == 'js'


def test_crawl_site_stealth_mode():
    """stealth 模式 → 走 crawl_stealth"""
    from crawler import crawl_site

    site = {'id': '4', 'name': '防护站点', 'url': 'https://cf.com',
            'status': 'no_rss', 'crawl_mode': 'stealth'}

    with patch('crawler.crawl_stealth', return_value=[{'title': 'T', 'url': 'U', 'published': ''}]) as mock_st:
        result = crawl_site(site)

    mock_st.assert_called_once_with(site)
    assert result['method'] == 'stealth'


def test_crawl_site_html_mode():
    """html 模式 → 强制走 crawl_html，即使有 RSS"""
    from crawler import crawl_site

    site = {'id': '5', 'name': 'Force HTML', 'url': 'https://force.com',
            'rss_url': 'https://force.com/feed', 'status': 'rss', 'crawl_mode': 'html'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': ''}]) as mock_html:
        result = crawl_site(site)

    mock_html.assert_called_once_with(site)
    assert result['method'] == 'html'


def test_crawl_site_no_crawl_mode_defaults_auto():
    """无 crawl_mode 字段 → 默认 auto"""
    from crawler import crawl_site

    site = {'id': '6', 'name': 'Old', 'url': 'https://old.com', 'status': 'no_rss'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': ''}]) as mock_html:
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
        'count': 1, 'items': [{'title': 'T', 'url': 'U', 'published': ''}],
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
