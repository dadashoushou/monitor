import re
from unittest.mock import MagicMock
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
