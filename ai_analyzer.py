"""
AI 网页结构分析器：调用 LLM API 分析页面 HTML，生成 CSS 选择器规则
"""
import re
import json
import requests
from datetime import datetime

SYSTEM_PROMPT = """你是一个网页结构分析专家。你的任务是分析网站首页 HTML，提取新闻/文章列表的抓取规则。

需要提取的信息：
1. 新闻标题 — 文章标题文本
2. 正文链接 — 文章详情页 URL
3. 发布时间 — 文章的发布时间

重要：大型门户网站（如凤凰网、新浪、网易等）的首页通常有多个板块（头条、财经、科技、娱乐等），新闻分散在不同区域。你的 CSS 选择器必须能覆盖页面中所有板块的文章链接，而不仅仅是某一个区域。优先使用能匹配全站文章链接的通用选择器，必要时可以用逗号分隔多个选择器。

分析步骤：
1. 遍历页面中所有区域，找到全部「新闻/文章列表」板块
2. 确定能选中所有板块中文章标题链接的 CSS 选择器（用逗号组合多个选择器）
3. 分析发布时间的来源：
   - 如果列表页 HTML 中有时间元素（如 <span class="time">、<time> 标签等），给出时间元素的 CSS 选择器
   - 如果时间嵌在文章 URL 中（如 /2026/04-17/xxx 或 /202604/content_xxx），给出从 URL 提取时间的正则
   - 如果列表页完全没有时间信息，time_source 设为 null

请严格按以下 JSON 格式返回，不要包含任何其他内容：
{
  "css_selector": "选中文章标题链接的 CSS 选择器",
  "url_pattern": "文章 URL 的正则表达式，用于过滤非文章链接，null 表示不过滤",
  "title_attr": "标题文本来源属性名，null 表示用 innerText",
  "time_source": "time_css 或 time_url 或 null",
  "time_css": "时间元素的 CSS 选择器（相对于文章条目的父容器），仅 time_source=time_css 时有值",
  "time_url_pattern": "从 URL 提取时间的正则（需包含命名分组 year/month/day），仅 time_source=time_url 时有值",
  "min_title_len": 8,
  "max_title_len": 80
}"""


def _strip_html(html: str) -> str:
    """深度清洗 HTML：只保留 AI 分析所需的结构信息（链接、文本、class/id），截取前 64KB"""
    flags = re.DOTALL | re.IGNORECASE
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=flags)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=flags)
    html = re.sub(r'<!--.*?-->', '', html, flags=flags)
    html = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=flags)
    html = re.sub(r'<noscript[^>]*>.*?</noscript>', '', html, flags=flags)
    html = re.sub(
        r'<(?:img|picture|video|audio|source|canvas|iframe|embed|object'
        r'|input|button|textarea|select|option|form)\b[^>]*/?>',
        '', html, flags=flags,
    )
    html = re.sub(r'\s(?:style|onclick|onload|onmouseover|onmouseout|onfocus|onblur|onerror|onsubmit)="[^"]*"', '', html, flags=flags)
    html = re.sub(r'\s(?:style|onclick|onload|onmouseover|onmouseout|onfocus|onblur|onerror|onsubmit)=\'[^\']*\'', '', html, flags=flags)
    html = re.sub(r'\sdata-[a-z0-9-]+="[^"]*"', '', html, flags=flags)
    html = re.sub(r'\ssrcset="[^"]*"', '', html, flags=flags)
    html = re.sub(r'\ssrc="data:[^"]*"', '', html, flags=flags)
    html = re.sub(r'\s+', ' ', html)
    return html[:65536]


def analyze_page(html: str, url: str, ai_config: dict,
                 progress_cb=None) -> dict:
    """调用 LLM API 分析页面结构，返回 selectors dict。

    参数:
        html: 原始页面 HTML
        url: 站点 URL
        ai_config: {"api_url": "...", "api_key": "...", "model": "..."}
        progress_cb: 可选回调函数，接收步骤名称字符串

    返回: selectors dict
    异常: ValueError（JSON 解析失败）、requests.RequestException（网络/API 错误）
    """
    if progress_cb:
        progress_cb('stripping_html')
    cleaned = _strip_html(html)

    if progress_cb:
        progress_cb('calling_ai')

    api_url = ai_config['api_url'].rstrip('/')
    if not api_url.endswith('/chat/completions'):
        api_url += '/chat/completions'

    resp = requests.post(
        api_url,
        json={
            'model': ai_config['model'],
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': f'网站 URL：{url}\n\nHTML 代码：\n{cleaned}'},
            ],
            'temperature': 0,
        },
        headers={
            'Authorization': f'Bearer {ai_config["api_key"]}',
            'Content-Type': 'application/json',
        },
        timeout=120,
    )
    resp.raise_for_status()

    if progress_cb:
        progress_cb('parsing_result')

    content = resp.json()['choices'][0]['message']['content'].strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)

    selectors = json.loads(content)
    selectors['generated_by'] = 'ai'
    selectors['generated_at'] = datetime.now().isoformat(timespec='seconds')
    return selectors
