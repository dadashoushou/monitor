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


def test_crawl_site_rss_with_stealth_article_fetch():
    """RSS 站点在 stealth 模式下应使用 StealthyFetcher 补抓正文"""
    from crawler import crawl_site

    site = {
        'id': 'rss-stealth',
        'name': 'RSS stealth site',
        'url': 'https://example.com',
        'rss_url': 'https://example.com/feed',
        'status': 'rss',
        'crawl_mode': 'stealth',
    }

    with patch(
        'crawler.crawl_rss',
        return_value=[{
            'title': 'T',
            'url': 'https://example.com/article-1',
            'published': None,
            'summary': 'S',
            'content': '',
            'crawled_at': '2026-04-18T00:00:00',
        }],
    ), patch('crawler.StealthyFetcher') as MockSF:
        mock_page = MagicMock()
        mock_page.css.return_value = []
        mock_page.text = 'Stealth article body text that is long enough to keep.'
        MockSF.fetch.return_value = mock_page

        result = crawl_site(site)

    MockSF.fetch.assert_called_once_with(
        'https://example.com/article-1',
        headless=True, network_idle=True, disable_resources=True, timeout=30000
    )
    assert result['method'] == 'rss'
    assert result['items'][0]['content']


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
    """RSS 站点的 html 策略仍应先走 RSS，再按 html 补抓正文"""
    from crawler import crawl_site

    site = {'id': '5', 'name': 'Force HTML', 'url': 'https://force.com',
            'rss_url': 'https://force.com/feed', 'status': 'rss', 'crawl_mode': 'html'}

    with patch('crawler.crawl_rss', return_value=[{'title': 'T', 'url': 'https://force.com/article-1', 'published': None, 'summary': 'S', 'content': '', 'crawled_at': '2026-04-18T00:00:00'}]) as mock_rss, \
         patch('crawler.Fetcher') as MockFetcher:
        mock_page = MagicMock()
        mock_page.css.return_value = []
        mock_page.text = 'Article body text that is long enough to keep.'
        MockFetcher.get.return_value = mock_page
        result = crawl_site(site)

    mock_rss.assert_called_once_with(site)
    MockFetcher.get.assert_called_once_with('https://force.com/article-1', timeout=15)
    assert result['method'] == 'rss'


def test_crawl_site_no_crawl_mode_defaults_auto():
    """无 crawl_mode 字段 → 默认 auto"""
    from crawler import crawl_site

    site = {'id': '6', 'name': 'Old', 'url': 'https://old.com', 'status': 'no_rss'}

    with patch('crawler.crawl_html', return_value=[{'title': 'T', 'url': 'U', 'published': None, 'crawled_at': '2026-04-18T00:00:00'}]) as mock_html:
        result = crawl_site(site)

    mock_html.assert_called_once_with(site)
    assert result['method'] == 'html'


def test_crawl_site_skips_known_urls_before_content_fetch():
    """历史 URL 会在正文抓取前被过滤，避免重复打开同一篇文章。"""
    from crawler import crawl_site

    site = {
        'id': '7',
        'name': 'Skip Known',
        'url': 'https://example.com',
        'status': 'no_rss',
        '_skip_urls': ['https://example.com/article-1'],
    }

    with patch(
        'crawler.crawl_html',
        return_value=[
            {'title': 'Old', 'url': 'https://example.com/article-1/', 'published': None, 'crawled_at': '2026-04-18T00:00:00'},
            {'title': 'New', 'url': 'https://example.com/article-2', 'published': None, 'crawled_at': '2026-04-18T00:00:00'},
        ],
    ), patch('crawler._attach_article_content') as mock_attach:
        mock_attach.side_effect = lambda items, site: [
            {**item, 'content': '正文内容'} for item in items
        ]
        result = crawl_site(site)

    assert result['count'] == 1
    assert result['items'][0]['url'] == 'https://example.com/article-2'
    mock_attach.assert_called_once()
    assert [item['url'] for item in mock_attach.call_args.args[0]] == ['https://example.com/article-2']


def test_extract_page_content_prefers_article_text():
    """详情页正文优先从 article 等正文容器提取。"""
    from crawler import _extract_page_content

    article = MagicMock()
    article.text = '这是第一段正文。' * 20
    page = MagicMock()
    page.css.side_effect = lambda selector: [article] if selector == 'article' else []

    assert _extract_page_content(page).startswith('这是第一段正文。')


def test_extract_page_content_supports_raw_html_content_selector():
    """站点专属正文容器应从原始 HTML 中提取，即使 Scrapling text 为空。"""
    from crawler import _extract_page_content

    page = MagicMock()
    page.body = (
        b'<html><body><div class="col-md-8 content-wrapper">'
        b'<span>Follow UST</span>'
        b'<p>This is the article body with enough text to pass the content threshold.</p>'
        b'</div></body></html>'
    )
    page.text = ''
    page.css.return_value = []

    content = _extract_page_content(page, 'div.col-md-8.content-wrapper')

    assert 'This is the article body' in content
    assert content


def test_attach_article_content_passes_site_content_selector():
    """正文抓取应把站点专属 content_selector 传给详情页抽取器。"""
    from crawler import _attach_article_content

    items = [{'title': 'T', 'url': 'https://example.com/article', 'content': ''}]
    site = {
        'crawl_mode': 'stealth',
        'content_selector': 'div.col-md-8.content-wrapper',
    }

    with patch(
        'crawler._crawl_article_content',
        return_value=('正文内容', '<html></html>'),
    ) as mock_content:
        result = _attach_article_content(items, site)

    assert result[0]['content'] == '正文内容'
    mock_content.assert_called_once_with(
        'https://example.com/article',
        'stealth',
        'div.col-md-8.content-wrapper',
    )


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


def test_defense_news_selector_covers_editorial_sections_and_excludes_special_pages():
    """Defense News 规则覆盖多级栏目，并排除视频和专题落地页。"""
    from crawler import _extract_articles

    hrefs = [
        '/industry/techwatch/2026/09/11/pentagon-looks-to-ai-to-identify-space-and-missile-threats/',
        '/news/pentagon-congress/2026/09/11/saudi-crown-prince-sought-us-military-help-with-houthis-sources-say/',
        '/global/2026/09/10/russia-sends-bones-of-medieval-warrior-prince-to-ukraine-front-to-boost-morale/',
        '/flashpoints/middle-east/2026/09/10/iran-attack-on-base-in-jordan-damaged-american-military-aircraft-us-official-says/',
        '/opinion/2026/09/03/chinese-military-analysts-cant-wait-for-the-us-navys-battleship-era/',
        '/video/2026/09/08/marines-to-add-thousands-to-ranks-in-coming-years-defense-news-weekly-full-episode-9826/',
        '/meta/2026/08/31/top-100-defense-companies-2026/',
    ]
    page = MagicMock()
    page.css.return_value = [
        _make_mock_element(f'Defense News article title {i} is long enough', href, {'href': href})
        for i, href in enumerate(hrefs)
    ]
    selectors = {
        'css_selector': 'article a[href]',
        'url_pattern': r'^(?:https?://(?:www\.)?defensenews\.com)?/(?!video(?:/|$)|meta(?:/|$))[^?#]*?/\d{4}/\d{2}/\d{2}/[^/?#]+/?$',
        'time_source': 'time_url',
        'time_url_pattern': r'/(?P<year>\d{4})/(?P<month>\d{2})/(?P<day>\d{2})/',
        'min_title_len': 12,
        'max_title_len': 140,
    }

    items = _extract_articles(page, 'https://www.defensenews.com/', selectors)

    assert len(items) == 5
    assert all('/video/' not in item['url'] and '/meta/' not in item['url'] for item in items)
    assert items[0]['published'] == '2026-09-11'


def test_defense_news_article_content_selector_extracts_raw_article():
    """Defense News 详情页的 article 容器可从原始 HTML 提取正文。"""
    from crawler import _extract_page_content

    page = MagicMock()
    page.body = (
        b'<html><body><article>'
        b'<p>Missile defense in wartime involves many complications.</p>'
        b'<p>The Pentagon now wants artificial intelligence that can cut through the confusion.</p>'
        b'</article></body></html>'
    )
    page.text = ''
    page.css.return_value = []

    content = _extract_page_content(page, 'article')

    assert 'Missile defense in wartime' in content
    assert 'The Pentagon now wants artificial intelligence' in content


def test_air_and_space_forces_article_content_selector_extracts_post_body():
    """Air & Space Forces 详情页应从 post-body 容器提取正文。"""
    from crawler import _extract_page_content

    page = MagicMock()
    page.body = (
        b'<html><main id="main"><div class="post-body">'
        b'<div class="author-date">Sept. 10, 2026 | By Author</div>'
        b'<p class="wp-block-paragraph">The article body contains the full report '
        b'and enough text to pass the content threshold for extraction.</p>'
        b'<h4 class="wp-block-heading">Section heading</h4>'
        b'<p class="wp-block-paragraph">A second paragraph keeps the article body '
        b'behavior representative of the live site structure.</p>'
        b'</div></main></html>'
    )
    page.text = ''
    page.css.return_value = []

    content = _extract_page_content(page, 'main#main .post-body')

    assert 'The article body contains the full report' in content
    assert 'Section heading' in content
    assert content


def test_afrl_article_content_selector_extracts_et_pb_post_content():
    """AFRL 详情页应从 RSS 链接对应的正文容器提取原文。"""
    from crawler import _extract_page_content

    page = MagicMock()
    page.body = (
        b'<html><body><div class="et_pb_post_content">'
        b'<p>The laboratory demonstrated a neural network control method '
        b'for an in-orbit satellite bus during a flight experiment.</p>'
        b'<p>The result supports future autonomous space operations and '
        b'provides enough text to represent the article body.</p>'
        b'</div></body></html>'
    )
    page.text = ''
    page.css.return_value = []

    content = _extract_page_content(page, '.et_pb_post_content')

    assert 'The laboratory demonstrated a neural network control method' in content
    assert 'future autonomous space operations' in content


def test_lockheed_news_selector_matches_new_news_hub_articles():
    """Lockheed 新新闻页规则应匹配内部 dated HTML 详情页。"""
    import re

    pattern = re.compile(
        r'(?:(?:https?://www\.lockheedmartin\.com)?/en-us/news/[^?#]*\d{4}[^?#]*\.html|https?://news\.lockheedmartin\.com/\d{4}-\d{2}-\d{2}-[^?#]+)(?:[?#].*)?$'
    )

    assert pattern.search(
        'https://www.lockheedmartin.com/en-us/news/features/2026/t-rex-demo.html'
    )
    assert pattern.search('/en-us/news/features/2026/t-rex-demo.html')
    assert pattern.search(
        'https://news.lockheedmartin.com/2026-09-10-example'
    )
    assert not pattern.search('https://www.lockheedmartin.com/en-us/news.html')


def test_lockheed_article_content_selector_extracts_main_body():
    """Lockheed 新站详情页应能从 main article-body 容器提取正文。"""
    from crawler import _extract_page_content

    page = MagicMock()
    page.body = (
        b'<html><main><div class="article-body">'
        b'<p>The battlespace is evolving and the need for survivable '
        b'autonomous capability is rapidly growing.</p>'
        b'<p>The program continues toward first flight in 2027 with '
        b'additional vehicles planned for production.</p>'
        b'</div></main></html>'
    )
    page.text = ''
    page.css.return_value = []

    content = _extract_page_content(page, ['main .article-body', 'main'])

    assert 'The battlespace is evolving' in content
    assert 'first flight in 2027' in content


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
