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

分析步骤：
1. 找到页面中「新闻/文章列表」区域
2. 确定能选中所有文章标题链接的 CSS 选择器
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
    """去除 script/style/注释，截取前 30KB"""
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)
    html = re.sub(r'\s+', ' ', html)
    return html[:30720]


def analyze_page(html: str, url: str, ai_config: dict) -> dict:
    """调用 LLM API 分析页面结构，返回 selectors dict。

    参数:
        html: 原始页面 HTML
        url: 站点 URL
        ai_config: {"api_url": "...", "api_key": "...", "model": "..."}

    返回: selectors dict
    异常: ValueError（JSON 解析失败）、requests.RequestException（网络/API 错误）
    """
    cleaned = _strip_html(html)

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

    content = resp.json()['choices'][0]['message']['content'].strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)

    selectors = json.loads(content)
    selectors['generated_by'] = 'ai'
    selectors['generated_at'] = datetime.now().isoformat(timespec='seconds')
    return selectors
