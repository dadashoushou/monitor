# 爬取管理功能设计文档

## 目标

为 openmonitor 添加内容抓取能力：定时自动抓取 + 手动立即抓取，结果存为 JSON 文件，管理界面展示抓取历史和文章列表。

## 架构

```
openmonitor/
├── app.py              # Flask + APScheduler，新增抓取 API
├── crawler.py          # 抓取引擎（RSS + BeautifulSoup）
├── sites.json          # 网站列表（已有）
├── data/               # 抓取结果目录（自动创建）
│   └── YYYY-MM-DD_HH-MM-SS_<site_id>.json
└── templates/
    └── index.html      # 管理界面（扩展）
```

## 数据存储

每次抓取若有新内容，写一个 JSON 文件到 `data/` 目录：

```json
{
  "site_id": "uuid",
  "site_name": "新华网",
  "site_url": "http://www.xinhuanet.com/",
  "crawled_at": "2026-04-15T10:30:00",
  "method": "rss",
  "count": 20,
  "items": [
    {"title": "文章标题", "url": "https://...", "published": "2026-04-15T08:00:00"}
  ]
}
```

- 文件名格式：`YYYY-MM-DD_HH-MM-SS_<site_id>.json`
- 若抓取结果为空（0条），不创建文件
- `method` 字段值：`rss`（feedparser 抓取）或 `html`（BeautifulSoup 抓取）

## crawler.py

### `crawl_rss(site) -> list[dict]`

用 feedparser 读取 `site['rss_url']`，返回条目列表：
```python
[{"title": str, "url": str, "published": str}]
```
- `published` 从 feedparser entry 的 `published_parsed` 或 `updated_parsed` 转为 ISO 格式字符串，无时间则为空字符串

### `crawl_html(site) -> list[dict]`

用 requests + BeautifulSoup 抓取 `site['url']` 首页，提取文章链接：
- 筛选条件：链接文字长度 8-80 字符，href 包含日期模式 `\d{4}[-/_]\d{2}`
- 尝试从链接的父元素或相邻元素提取时间（`<time>` 标签或含日期的文本），无法提取则 `published` 为空字符串
- 返回格式同上，最多返回 30 条

### `crawl_site(site) -> dict | None`

- 若 `site['status'] == 'rss'`：调用 `crawl_rss`
- 否则：调用 `crawl_html`
- 若结果为空列表，返回 `None`（不写文件）
- 否则写文件到 `data/` 目录，返回结果 dict

### `crawl_all(sites) -> list[dict]`

用 `ThreadPoolExecutor(max_workers=5)` 并发执行所有网站，返回结果列表。

## app.py 新增

### 定时器

启动时用 APScheduler 注册定时任务：
```python
scheduler = BackgroundScheduler()
scheduler.add_job(run_crawl_all, 'interval', hours=6, id='crawl_job')
scheduler.start()
```

间隔可通过 `config.json` 持久化（字段 `crawl_interval_hours`，默认 6）。

### 新增 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/crawl` | 手动触发全部抓取（后台线程） |
| POST | `/api/crawl/<site_id>` | 手动触发单个网站抓取 |
| GET | `/api/crawl/status` | 当前抓取进度 |
| GET | `/api/config` | 获取配置（含定时间隔） |
| POST | `/api/config` | 更新配置（修改定时间隔） |
| GET | `/api/results/<site_id>` | 某网站的历史抓取文件列表 |
| GET | `/api/results/<site_id>/<filename>` | 某次抓取的完整内容 |

### 抓取状态结构

```python
crawl_state = {
    'running': False,
    'total': 0,
    'done': 0,
    'current': '',
    'last_run': None,   # ISO 时间字符串
}
```

## index.html 变化

### 表格新增列

- "最近条目数"：读取该网站最新一个 data 文件的 `count` 字段
- "上次抓取"：最新 data 文件的 `crawled_at`

### 顶部工具栏

- 新增"全部抓取"按钮（与"全部检测"并列）
- 定时间隔下拉：1h / 6h / 12h / 24h，选择后调用 `POST /api/config`

### 操作列

- 新增"抓取"按钮（单个网站立即抓取）

### 历史面板

- 点击网站名称 → 右侧或弹窗展示该网站抓取历史列表（时间、条目数、方式）
- 点击某条历史记录 → 展开显示文章列表（标题可点击跳转原文）

## 依赖

```
apscheduler
beautifulsoup4  # 已在 analyze_sites.py 中使用
feedparser      # 已有
requests        # 已有
```
