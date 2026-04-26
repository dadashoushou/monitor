# OpenMonitor 前端数据流转分析

## 架构概览

```
┌─────────────┐         ┌─────────────┐         ┌─────────────┐
│   Browser   │ ◄─────► │ Flask API   │ ◄─────► │ File System │
│  (前端 JS)   │  HTTP   │  (app.py)   │  I/O    │ (JSON 文件)  │
└─────────────┘         └─────────────┘         └─────────────┘
```

## 核心数据流

### 1. 页面初始化流程

```javascript
// 页面加载时执行（第 716-719 行）
loadSitesWithCrawlInfo();  // 加载站点列表 + 抓取信息
initIntervalSelect();       // 初始化配置选择器
showIdleStatus();          // 显示状态栏
loadAIConfig();            // 加载前端 AI 配置
```

**详细流程：**

```
┌─ loadSitesWithCrawlInfo() ─────────────────────────────┐
│                                                          │
│  1. GET /api/sites → 获取所有站点基础信息                │
│     返回: [{id, name, url, status, crawl_mode, ...}]    │
│                                                          │
│  2. 并行请求每个站点的抓取历史                            │
│     GET /api/results/{site_id} → 获取抓取记录列表        │
│     返回: [{filename, crawled_at, count, method}]       │
│                                                          │
│  3. 合并数据：将最新抓取信息附加到站点对象                │
│     site.crawl_count = results[0].count                 │
│     site.last_crawled = results[0].crawled_at           │
│                                                          │
│  4. renderTable(sites) → 渲染表格                        │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

### 2. 配置管理流程

#### 2.1 读取配置（第 402-424 行）

```javascript
// initIntervalSelect()
GET /api/config
  ↓
返回: {
  crawl_interval_hours: 1,
  data_dir: "D:/data",
  max_article_age_days: 0
}
  ↓
更新前端控件值
```

#### 2.2 保存配置

**抓取间隔：**
```javascript
// 第 407-413 行
intervalSelect.addEventListener('change', async () => {
  POST /api/config
  Body: { crawl_interval_hours: parseInt(value) }
});
```

**数据目录：**
```javascript
// 第 593-615 行
btnSaveDataDir.click → 
  POST /api/config
  Body: { data_dir: input.value.trim() }
    ↓
  后端验证路径 (app.py 第 416-419 行)
    ↓
  保存到 config.json
```

**时效过滤：**
```javascript
// 第 417-423 行
ageSelect.addEventListener('change', async () => {
  POST /api/config
  Body: { max_article_age_days: parseInt(value) }
});
```

### 3. 站点管理流程

#### 3.1 添加站点

```
用户点击 "+ 添加网站" (第 121 行)
  ↓
openModal() → 打开弹窗 (第 502-532 行)
  ↓
用户填写表单 (name, url, crawl_mode, note)
  ↓
saveSite() → POST /api/sites (第 542-559 行)
  Body: { name, url, note, crawl_mode }
  ↓
后端生成 UUID，保存到 sites.json (app.py 第 174-199 行)
  ↓
closeModal() + loadSitesWithCrawlInfo() → 刷新列表
```

#### 3.2 编辑站点

```
用户点击 "编辑" 按钮 (第 473 行)
  ↓
openModal(site_id) (第 502-532 行)
  ↓
GET /api/sites → 查找站点数据 (第 511 行)
  ↓
填充表单 (第 513-517 行)
  ↓
用户修改后点击 "保存"
  ↓
saveSite() → PUT /api/sites/{id} (第 551-552 行)
  ↓
后端更新 sites.json (app.py 第 202-221 行)
  ↓
刷新列表
```

#### 3.3 删除站点

```
用户点击 "删除" 按钮 (第 474 行)
  ↓
deleteSite(id) → 确认弹窗 (第 496-500 行)
  ↓
DELETE /api/sites/{id}
  ↓
后端从 sites.json 移除 (app.py 第 224-231 行)
  ↓
loadSites() → 刷新列表
```

### 4. RSS 检测流程

#### 4.1 单个站点检测

```
用户点击 "检测" 按钮 (第 469 行)
  ↓
checkOne(id) (第 484-494 行)
  ↓
更新 UI 状态: badge → "检测中…"
  ↓
POST /api/check/{id}
  ↓
后端执行 RSS 检测 (app.py 第 291-301 行)
  - 尝试 <link> 标签
  - 尝试常见路径 (/feed, /rss.xml...)
  - 扫描页面链接
  ↓
更新 sites.json: {rss_url, status, last_checked}
  ↓
前端刷新列表，显示新状态
```

#### 4.2 批量检测

```
用户点击 "全部检测" (第 103 行)
  ↓
btnCheckAll.click (第 561-567 行)
  ↓
POST /api/check → 启动后台线程 (app.py 第 328-334 行)
  ↓
startPolling() → 开始轮询状态 (第 569-585 行)
  ↓
每 1.5 秒请求 GET /api/check/status
  返回: {running, total, done, current}
  ↓
更新状态栏进度条 (第 575 行)
  ↓
检测完成: running=false
  ↓
停止轮询，刷新列表
```

### 5. 内容抓取流程

#### 5.1 单个站点抓取

```
用户点击 "抓取" 按钮 (第 470 行)
  ↓
crawlOne(id) (第 316-323 行)
  ↓
POST /api/crawl/{id}
  ↓
后端执行抓取 (app.py 第 372-396 行)
  1. 加载站点配置
  2. 调用 crawler.py 抓取内容
  3. 去重：加载历史 URL，过滤已抓取
  4. 保存到 data_dir/{timestamp}_{site_id}.json
  ↓
返回抓取结果: {count, items, method, ...}
  ↓
前端刷新列表，显示最新抓取时间和条目数
```

#### 5.2 批量抓取

```
用户点击 "全部抓取" (第 104 行)
  ↓
btnCrawlAll.click (第 617-623 行)
  ↓
POST /api/crawl → 启动后台线程 (app.py 第 356-363 行)
  ↓
startCrawlPolling() → 开始轮询 (第 325-345 行)
  ↓
每 1.5 秒请求 GET /api/crawl/status
  返回: {running, total, done, current}
  ↓
更新状态栏: "抓取中 3/10：新华网"
  ↓
抓取完成: running=false
  ↓
停止轮询，刷新列表
```

### 6. 历史记录查看流程

```
用户点击 "历史" 按钮 (第 472 行)
  ↓
showHistory(siteId, siteName) (第 347-372 行)
  ↓
GET /api/results/{site_id}
  ↓
后端扫描 data_dir/*_{site_id}.json (app.py 第 427-446 行)
  返回: [{filename, crawled_at, count, method}]
  ↓
渲染历史列表 (第 360-366 行)
  ↓
用户点击某条历史记录
  ↓
showArticles(siteId, filename) (第 374-400 行)
  ↓
GET /api/results/{site_id}/{filename}
  ↓
后端读取 JSON 文件 (app.py 第 449-457 行)
  返回: {items: [{title, url, published}]}
  ↓
检测英文标题 → 调用 AI 翻译 (第 388-395 行)
  ↓
渲染文章列表 (第 397-399 行)
```

### 7. AI 分析流程

```
用户点击 "AI分析" 按钮 (第 471 行)
  ↓
analyzeSiteById(id) (第 630-635 行)
  ↓
POST /api/sites/{id}/analyze
  ↓
后端启动分析线程 (app.py 第 524-546 行)
  1. 检查 AI 配置 (config.json 的 ai 字段)
  2. 启动后台线程执行 _run_analyze()
  ↓
startAnalyzePolling() → 轮询状态 (第 678-714 行)
  ↓
每 1.5 秒请求 GET /api/analyze/status
  返回: {running, step, message}
  步骤: fetching_page → stripping_html → calling_ai → parsing_result → saving → done
  ↓
分析完成: step='done'
  ↓
GET /api/analyze/result
  返回: {selectors, preview, preview_count}
  ↓
显示在弹窗预览区 (第 695-702 行)
  ↓
保存到 sites.json 的 selectors 字段
```

## 数据存储结构

### sites.json
```json
[
  {
    "seq": 1,
    "id": "uuid-xxx",
    "name": "新华网",
    "url": "https://example.com",
    "note": "备注",
    "rss_url": "https://example.com/rss.xml",
    "status": "rss",
    "last_checked": "2026-04-20T10:30:00",
    "crawl_mode": "auto",
    "selectors": {
      "css_selector": ".article",
      "title_selector": "h2",
      "link_selector": "a",
      "date_selector": ".date"
    }
  }
]
```

### config.json
```json
{
  "crawl_interval_hours": 1,
  "data_dir": "./data",
  "max_article_age_days": 3,
  "max_items": 200,
  "ai": {
    "api_url": "https://api.openai.com/v1",
    "api_key": "<your-api-key>",
    "model": "<your-model-name>"
  }
}
```

### data/{timestamp}_{site_id}.json
```json
{
  "site_id": "uuid-xxx",
  "site_name": "新华网",
  "site_url": "https://example.com",
  "method": "rss",
  "count": 15,
  "crawled_at": "2026-04-20T10:30:00",
  "items": [
    {
      "title": "文章标题",
      "url": "https://example.com/article/1",
      "published": "2026-04-20T09:00:00"
    }
  ]
}
```

## 关键设计模式

### 1. 轮询模式（Polling）
- 用于长时间任务（检测、抓取、AI 分析）
- 每 1.5 秒请求状态接口
- 显示实时进度和当前处理项

### 2. 乐观更新（Optimistic UI）
- 点击按钮立即禁用并更新文本
- 请求完成后恢复状态
- 提升用户体验

### 3. 并行请求（Parallel Fetching）
- `loadSitesWithCrawlInfo()` 使用 `Promise.all()`
- 同时请求所有站点的抓取历史
- 减少总加载时间

### 4. 增量加载（Lazy Loading）
- 历史记录点击时才加载文章列表
- 避免一次性加载大量数据

### 5. 去重机制（Deduplication）
- 后端抓取时加载历史 URL
- 过滤已抓取的文章
- 只保存新增内容

## 数据目录的作用

**用户设置的 `data_dir` 路径：**

1. **不是前端读取源** — 前端无法直接访问文件系统
2. **是后端存储位置** — 抓取结果保存到此目录
3. **通过 API 访问** — 前端通过 `/api/results/*` 读取

**流程：**
```
前端设置路径 → config.json (data_dir)
                     ↓
              后端抓取时使用
                     ↓
           保存到 data_dir/*.json
                     ↓
前端请求 → API 读取文件 → 返回 JSON
```

## 状态管理

### 前端状态
- `editingId` — 当前编辑的站点 ID
- `pollTimer` — 检测轮询定时器
- `crawlPollTimer` — 抓取轮询定时器
- `analyzePollTimer` — AI 分析轮询定时器
- `aiConfig` — 前端 AI 配置（用于翻译）

### 后端状态（内存）
- `check_state` — 检测进度
- `crawl_state` — 抓取进度
- `analyze_state` — AI 分析进度

## 性能优化点

1. **并行请求** — 站点列表和抓取历史并行加载
2. **轮询间隔** — 1.5 秒平衡实时性和服务器压力
3. **按需加载** — 文章列表点击时才加载
4. **去重过滤** — 避免重复抓取和存储
5. **时效过滤** — 只抓取指定天数内的文章

## 错误处理

1. **网络错误** — try-catch 捕获，console.error 记录
2. **API 错误** — 检查 response.ok，显示错误信息
3. **超时处理** — 后端设置超时，前端显示超时状态
4. **空数据处理** — 显示 "暂无记录" 提示
5. **配置缺失** — AI 功能检查配置完整性

## API 接口清单

### 站点管理
- `GET /api/sites` — 获取所有站点
- `POST /api/sites` — 添加站点
- `PUT /api/sites/{id}` — 更新站点
- `DELETE /api/sites/{id}` — 删除站点

### RSS 检测
- `POST /api/check` — 批量检测
- `POST /api/check/{id}` — 单个检测
- `GET /api/check/status` — 检测状态

### 内容抓取
- `POST /api/crawl` — 批量抓取
- `POST /api/crawl/{id}` — 单个抓取
- `GET /api/crawl/status` — 抓取状态

### 配置管理
- `GET /api/config` — 获取配置
- `POST /api/config` — 更新配置

### 结果查询
- `GET /api/results/{site_id}` — 获取抓取历史列表
- `GET /api/results/{site_id}/{filename}` — 获取具体抓取结果

### AI 分析
- `POST /api/sites/{id}/analyze` — 启动 AI 分析
- `GET /api/analyze/status` — 分析状态
- `GET /api/analyze/result` — 分析结果

### 系统状态
- `GET /api/system/status` — 系统状态（定时任务）
