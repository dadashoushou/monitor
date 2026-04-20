# OpenMonitor

网站内容监控与抓取工具，带 Web 管理界面、RSS 检测、多抓取模式和可选 AI 规则分析。

## 功能

- 添加、编辑、删除监控站点
- 自动检测 RSS，并在 RSS / HTML / JS / stealth 模式之间切换
- 基于 Scrapling 抓取静态页、动态页和带反爬保护的页面
- 使用 AI 生成选择器规则，并缓存到本地站点配置
- 支持定时抓取、手动抓取、历史结果查看和增量去重
- 支持文章时效过滤和统一状态栏进度反馈

## 技术栈

- 后端：Python 3.12 + Flask
- 抓取引擎：[Scrapling](https://github.com/D4Vinci/Scrapling)
- RSS 解析：feedparser
- AI 分析：任意 OpenAI 兼容接口
- 前端：Jinja2 模板
- 存储：本地 JSON 文件

## 快速启动

```bash
pip install flask requests feedparser apscheduler scrapling
python app.py
```

默认访问地址：`http://localhost:5000`

## 配置

复制 `config.example.json` 为 `config.json`，填入你自己的运行参数：

```json
{
  "crawl_interval_hours": 6,
  "data_dir": "",
  "max_items": 200,
  "max_article_age_days": 0,
  "ai": {
    "api_url": "https://api.openai.com/v1",
    "api_key": "<your-api-key>",
    "model": "<your-model-name>"
  }
}
```

| 字段 | 说明 |
|------|------|
| `crawl_interval_hours` | 定时抓取间隔（小时） |
| `data_dir` | 抓取结果保存目录，留空时使用 `./data` |
| `max_items` | 单站点最大抓取条数 |
| `max_article_age_days` | 文章时效过滤天数，`0` 表示不过滤 |
| `ai.api_url` | OpenAI 兼容接口地址 |
| `ai.api_key` | 你的 API 密钥 |
| `ai.model` | 你的模型名 |

## AI 分析流程

点击站点的“AI 分析”后，系统会：

1. 抓取目标页面 HTML
2. 清洗噪音内容并截断到安全大小
3. 调用 LLM 生成 CSS 选择器、URL 过滤和时间提取规则
4. 将规则写入本地 `sites.json`，后续抓取直接复用

未配置 AI 时，系统会回退到内置抓取逻辑。

## 公开仓库说明

本仓库不会提交以下本地文件或产物：

- `config.json`
- `sites.json`
- `state.json`
- `data/`
- `raw/`
- `graphify-out/`
- `frontend/graphify-out/`
- `frontend/config.json`
- `frontend/state.json`
- 各类测试缓存和图谱缓存

发布前检查见 [docs/PUBLIC_REPO_GUIDE.md](docs/PUBLIC_REPO_GUIDE.md)。

## 项目结构

```text
.
├── app.py
├── ai_analyzer.py
├── crawler.py
├── config.example.json
├── templates/
├── tests/
├── docs/
└── frontend/
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/sites` | 站点 CRUD |
| PUT/DELETE | `/api/sites/<id>` | 更新或删除站点 |
| POST | `/api/check` | 批量检测 RSS |
| POST | `/api/crawl` | 批量抓取 |
| POST | `/api/crawl/<id>` | 单站点抓取 |
| POST | `/api/sites/<id>/analyze` | AI 分析站点结构 |
| GET/POST | `/api/config` | 读取或更新运行配置 |
| GET | `/api/results/<id>` | 查看抓取历史 |
