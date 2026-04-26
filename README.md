# OpenMonitor

网站内容监控与抓取工具，提供 Flask 管理界面、RSS 检测、多抓取模式、历史查看和可选 AI 选择器分析。

## 功能

- 管理监控站点：新增、编辑、删除
- 自动检测 RSS，并在 `rss` / `html` / `js` / `stealth` 模式之间切换
- 支持定时抓取、批量抓取、单站点抓取
- 支持站点级暂停抓取、批量抓取停止、调度开关
- 支持文章时效过滤
- 支持抓取历史查看
- 支持基于标题索引的增量去重
- 支持 AI 分析页面结构并生成 selectors

## 技术栈

- Python 3.12
- Flask
- APScheduler
- feedparser
- Scrapling

## 快速启动

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item config.example.json config.json
python app.py
```

默认访问地址：`http://127.0.0.1:5000`

## 配置

`config.example.json`:

```json
{
  "crawl_interval_hours": 1,
  "data_dir": "",
  "mirror_data_dir": "",
  "max_items": 200,
  "max_article_age_days": 0,
  "ai": {
    "api_url": "https://api.openai.com/v1",
    "api_key": "<your-api-key>",
    "model": "<your-model-name>"
  }
}
```

关键字段：

- `crawl_interval_hours`: 定时抓取间隔，范围 `1-12` 小时
- `data_dir`: 抓取结果 JSON 保存目录，留空时默认使用 `./data`
- `mirror_data_dir`: 标题索引目录，留空时默认使用 `./history_mirror`
- `max_items`: 单站点单次最多保留的文章数
- `max_article_age_days`: 文章时效过滤天数，`0` 表示不过滤
- `ai`: 可选 AI 配置，用于页面结构分析

## History Mirror

- `mirror_data_dir` 现在默认指向 `./history_mirror`
- `history_mirror` 只保存每个站点的标题索引文件
- 索引文件包含 `site_id`、`site_url`、`updated_at`、`titles`
- 去重规则按 `site_id + 规范化标题` 比对
- 历史去重只读取 `history_mirror`，不读取 `data_dir`
- 不再保存镜像抓取快照文件

## AI 分析流程

1. 抓取目标页面 HTML
2. 清洗噪音内容并裁剪到安全大小
3. 调用 LLM 生成 CSS 选择器、URL 过滤和时间提取规则
4. 将规则写入本地 `sites.json`，后续抓取直接复用

## 本地文件

以下内容属于本地运行状态或敏感配置，不应提交到公共仓库：

- `config.json`
- `sites.json`
- `state.json`
- `data/`
- `raw/`
- `history_mirror/`
- `graphify-out/`
- 各类测试缓存目录

## 项目结构

```text
.
├── app.py
├── ai_analyzer.py
├── crawler.py
├── mirror_store.py
├── config.example.json
├── requirements.txt
├── templates/
├── tests/
└── docs/
```

## API

- `GET /api/sites`
- `POST /api/sites`
- `PUT /api/sites/<id>`
- `DELETE /api/sites/<id>`
- `POST /api/sites/<id>/crawl-toggle`
- `POST /api/check`
- `POST /api/check/<id>`
- `POST /api/crawl`
- `POST /api/crawl/<id>`
- `POST /api/crawl/stop`
- `GET /api/crawl/status`
- `POST /api/sites/<id>/analyze`
- `GET/POST /api/config`
- `GET /api/results/<id>`
- `GET /api/results/<id>/<filename>`
- `GET /api/system/status`
- `GET /api/system/stats`
- `POST /api/system/crawl-service`
