# OpenMonitor — 抓取模式功能 PRD

> 版本: v1.0 | 日期: 2026-04-17 | 状态: 设计中

---

## 1. 背景与动机

OpenMonitor 当前的抓取引擎仅支持两种方式：

| 方式 | 实现 | 局限 |
|------|------|------|
| RSS | feedparser | 依赖站点提供 RSS，覆盖面有限 |
| HTML | requests + BeautifulSoup | 无法处理 JS 渲染页面，无反检测能力 |

越来越多的新闻/内容站点采用 SPA 架构或部署了 bot 防护（Cloudflare、Akamai 等），现有方案无法有效抓取这些站点的内容。

## 2. 目标

引入 **Scrapling** 库，为每个监控站点提供可配置的抓取模式（`crawl_mode`），覆盖以下场景：

| 模式 | 场景 | 引擎 |
|------|------|------|
| `auto` | 默认，有 RSS 走 RSS，否则回退 HTML | feedparser / Scrapling Fetcher |
| `html` | 静态服务端渲染站点 | Scrapling Fetcher |
| `js` | SPA / 重度 JS 渲染站点 | Scrapling DynamicFetcher |
| `stealth` | 有 bot 防护的站点 | Scrapling StealthyFetcher |

## 3. 非目标

- 不改变现有 RSS 检测逻辑（`_detect_rss`、`_is_valid_feed`）
- 不引入代理池或 IP 轮换
- 不做内容解析/正文提取（仅抓取文章链接列表）
- 不修改数据存储格式（仍为 JSON 文件）

## 4. 功能需求

### 4.1 crawler.py — 抓取引擎重构

#### 4.1.1 公共提取函数

```
_extract_articles(page, site_url) -> list[dict]
```

- 接收 Scrapling Response 对象
- 复用现有的标题长度过滤（8-80 字符）和日期 URL 模式匹配
- 提取 `title`、`url`、`published` 三个字段
- 最多返回 30 条

#### 4.1.2 抓取函数

| 函数 | 引擎 | 关键参数 |
|------|------|----------|
| `crawl_html(site)` | `Fetcher.get()` | `stealthy_headers=True, timeout=10` |
| `crawl_js(site)` | `DynamicFetcher.fetch()` | `headless=True, network_idle=True, disable_resources=True, timeout=30000` |
| `crawl_stealth(site)` | `StealthyFetcher.fetch()` | `headless=True, network_idle=True, disable_resources=True, timeout=30000` |
| `crawl_rss(site)` | 不变 | feedparser |

#### 4.1.3 路由逻辑

```
crawl_site(site) 决策树:

  crawl_mode = site.get('crawl_mode', 'auto')

  if crawl_mode == 'auto':
      if site.status == 'rss' → crawl_rss()
      else → crawl_html()
  elif crawl_mode == 'html':
      → crawl_html()
  elif crawl_mode == 'js':
      → crawl_js()
  elif crawl_mode == 'stealth':
      → crawl_stealth()
```

#### 4.1.4 并发策略

```
crawl_all() 分组并发:

  静态站点 (rss, html, auto)  → ThreadPoolExecutor(max_workers=5)
  动态站点 (js, stealth)      → ThreadPoolExecutor(max_workers=2)
```

### 4.2 app.py — API 层适配

| 端点 | 变更 |
|------|------|
| `POST /api/sites` | 接收 `crawl_mode` 字段，默认 `"auto"` |
| `PUT /api/sites/<id>` | 支持修改 `crawl_mode` |
| 其他端点 | 不变 |

向后兼容：已有站点无 `crawl_mode` 字段时，读取默认为 `"auto"`。

### 4.3 templates/index.html — 前端 UI

| 区域 | 变更 |
|------|------|
| 站点表格 | 新增"抓取模式"列，显示模式 badge |
| 添加/编辑弹窗 | 新增"抓取模式"下拉选择器 |
| CSS | 新增 `.badge-auto`、`.badge-html`、`.badge-js`、`.badge-stealth` |
| JS | `STATUS_LABEL` 新增模式映射；`saveSite()` 提交 `crawl_mode`；`renderTable()` 渲染模式列 |

## 5. 技术依赖

| 依赖 | 用途 | 安装 |
|------|------|------|
| scrapling | 静态/动态/隐蔽抓取 | `pip install scrapling` |
| playwright (scrapling 内部) | 无头浏览器 | scrapling 自动安装 |

现有依赖不变：requests, feedparser, beautifulsoup4, apscheduler, flask

## 6. 数据模型变更

### sites.json 站点对象

```json
{
  "id": "uuid",
  "name": "站点名称",
  "url": "https://example.com",
  "note": "备注",
  "rss_url": null,
  "status": "pending",
  "last_checked": null,
  "crawl_mode": "auto"    // ← 新增字段
}
```

无需数据迁移，缺失字段读取时默认 `"auto"`。

## 7. 实施阶段

| 阶段 | 内容 | 文件 | 预估工作量 |
|------|------|------|-----------|
| P0 | crawler.py 重写 | `crawler.py` | 核心，最先实施 |
| P1-a | API 层适配 | `app.py` | 小改动 |
| P1-b | 前端 UI 更新 | `templates/index.html` | 中等改动 |
| P2 | 集成验证 | 全部 | 端到端测试 |

## 8. 验收标准

- [ ] 添加站点时可选择 auto / html / js / stealth 模式
- [ ] 编辑站点时可修改抓取模式
- [ ] 站点表格正确显示模式 badge
- [ ] auto 模式：有 RSS 的站点走 RSS，无 RSS 走 HTML
- [ ] html 模式：使用 Scrapling Fetcher 正常抓取静态站点
- [ ] js 模式：使用 DynamicFetcher 正常抓取 JS 渲染站点（如 newsnow.com）
- [ ] stealth 模式：使用 StealthyFetcher 正常抓取有防护的站点
- [ ] 全部抓取时并发控制正常（静态 5 并发，动态 2 并发）
- [ ] 已有站点无 crawl_mode 字段时默认 auto，无需手动迁移

## 9. 相关文档

| 文档 | 路径 | 说明 |
|------|------|------|
| 设计规范 | `docs/DESIGN_SPEC.md` | UI 配色、Badge、组件、交互规范 |
| 视觉设计稿 | `design/mockup.html` | 浏览器可预览的完整 UI mockup |
| 进度追踪 | `docs/PROGRESS.md` | 实施进度，支持断点恢复 |
| 原始企划 | 本地需求记录（未纳入仓库） | 用户原始需求文档 |
