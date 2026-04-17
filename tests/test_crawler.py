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
