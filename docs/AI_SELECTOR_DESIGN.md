# 方案 B：AI 离线分析 + 规则缓存 — 设计文档

## 一、问题回顾

当前 `_extract_articles()` 依赖硬编码的 URL 模式（日期正则 + `/article/`）来识别文章链接。
每接入一个新站点，如果 URL 结构不匹配已有模式，就必须改代码、加正则。

**核心矛盾**：规则是死的，网站结构是活的。

## 二、方案概述

```
┌──────────────────────────────────────────────────────────────┐
│                    添加/编辑站点时                              │
│                                                              │
│  用户点击「AI 分析」按钮                                        │
│       │                                                      │
│       ▼                                                      │
│  后端抓取目标页面 HTML                                          │
│       │                                                      │
│       ▼                                                      │
│  去除 script/style/注释 → 截取前 30KB → 构造 prompt            │
│       │                                                      │
│       ▼                                                      │
│  调用 LLM API（OpenAI 兼容接口）                                │
│       │                                                      │
│       ▼                                                      │
│  LLM 返回 JSON：                                              │
│  {                                                           │
│    "css_selector": "a[href*='/article/']",                   │
│    "url_pattern": "/article/[A-Z0-9]+\\.html$",             │
│    "title_attr": null,                                       │
│    "time_source": "time_url",                                │
│    "time_css": null,                                         │
│    "time_url_pattern": "/(?P<year>\\d{4})[-/](?P<month>..)", │
│    "min_title_len": 8,                                       │
│    "max_title_len": 80                                       │
│  }                                                           │
│       │                                                      │
│       ▼                                                      │
│  存入 sites.json 的 selectors 字段                            │
│  后续每次抓取直接使用缓存规则，不再调 AI                           │
└──────────────────────────────────────────────────────────────┘
```

**一句话总结**：AI 只在「添加站点 / 手动触发」时调用一次，生成 CSS 选择器规则缓存到配置，后续抓取零 AI 开销。

## 三、数据结构变更

### 3.1 sites.json — 新增 `selectors` 字段

```json
{
  "id": "31e01d53-...",
  "name": "网易新闻",
  "url": "https://news.163.com/",
  "crawl_mode": "html",
  "status": "no_rss",
  "selectors": {
    "css_selector": "a[href*='/article/']",
    "url_pattern": "/article/[A-Z0-9]+\\.html$",
    "title_attr": null,
    "time_source": "time_url",
    "time_css": null,
    "time_url_pattern": "/(?P<year>\\d{4})[-/](?P<month>\\d{2})[-/](?P<day>\\d{2})/",
    "min_title_len": 8,
    "max_title_len": 80,
    "generated_by": "ai",
    "generated_at": "2026-04-17T20:00:00"
  }
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `css_selector` | string | CSS 选择器，用于 `page.css(...)` 定位文章链接 |
| `url_pattern` | string\|null | 正则，进一步过滤 href（可选，null 表示不过滤） |
| `title_attr` | string\|null | 标题来源属性（null = 取 innerText，`"title"` = 取 title 属性） |
| `time_source` | string\|null | 时间来源：`"time_css"` / `"time_url"` / `null` |
| `time_css` | string\|null | 时间元素的 CSS 选择器（相对于文章条目的父容器） |
| `time_url_pattern` | string\|null | 从 URL 提取时间的正则（含命名分组 year/month/day） |
| `min_title_len` | int | 标题最小长度 |
| `max_title_len` | int | 标题最大长度 |
| `generated_by` | string | `"ai"` 或 `"manual"`，标记规则来源 |
| `generated_at` | string | 生成时间 |

**向后兼容**：`selectors` 为 null 或不存在时，走当前的硬编码逻辑（DATE_PATTERN + ARTICLE_PATTERN），老数据无需迁移。

### 3.2 config.json — 新增 AI 配置

```json
{
  "crawl_interval_hours": 1,
  "data_dir": "./data",
  "ai": {
    "api_url": "https://api.openai.com/v1",
    "api_key": "<your-api-key>",
    "model": "<your-model-name>"
  }
}
```

支持任何 OpenAI 兼容接口（OpenAI / Claude / DeepSeek / 本地 Ollama 等）。

## 四、Prompt 设计

### System Prompt

```
你是一个网页结构分析专家。你的任务是分析网站首页 HTML，提取新闻/文章列表的抓取规则。

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
}
```

### User Prompt

```
网站 URL：{url}

HTML 代码：
{truncated_html}
```

### HTML 预处理

发送前对 HTML 进行压缩：
1. 移除 `<script>...</script>` 标签及内容
2. 移除 `<style>...</style>` 标签及内容
3. 移除 HTML 注释 `<!--...-->`
4. 截取前 30KB（约 10000 tokens）

## 五、API 端点

### 新增端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/sites/<site_id>/analyze` | 触发 AI 分析，返回 selectors + 预览结果 |
| GET | `/api/config/ai` | 获取 AI 配置（api_key 脱敏） |
| POST | `/api/config/ai` | 保存 AI 配置 |

### 修改端点

| 方法 | 路径 | 变更 |
|------|------|------|
| POST | `/api/sites` | 接收 selectors 字段 |
| PUT | `/api/sites/<site_id>` | 接收 selectors 字段 |

## 六、完整调用流程

```
场景 1：添加新站点 + AI 分析
────────────────────────
用户填写名称、URL → 保存 → 点击「AI 分析」
  → POST /api/sites/{id}/analyze
  → 后端抓取页面 → 调 LLM → 返回 selectors + 预览
  → 前端显示分析结果
  → selectors 写入 sites.json
  → 后续抓取使用 selectors 规则

场景 2：不用 AI
──────────────
用户填写名称、URL → 直接保存
  → selectors 为 null
  → 抓取时走硬编码规则（完全兼容）

场景 3：站点改版，规则失效
────────────────────────
用户发现抓取结果为空
  → 点击「AI 分析」重新生成 selectors
  → 覆盖旧规则
```

## 七、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| LLM 返回格式不合法 | 解析失败 | JSON 解析 + try/except，失败时提示用户重试 |
| LLM 生成的选择器不准确 | 抓取结果质量差 | 分析完立即试抓一次，前端展示预览结果供用户确认 |
| HTML 过大超出 token 限制 | API 报错 | 截取前 30KB + 移除 script/style 标签压缩体积 |
| API Key 泄露 | 安全风险 | 前端显示为密码框，GET 接口脱敏返回 |
| 网站改版导致缓存规则失效 | 抓取为空 | 抓取结果为空时前端提示「规则可能失效，建议重新 AI 分析」 |
| AI API 不可用 | 功能降级 | selectors 为空时自动降级到硬编码规则，不影响已有功能 |
