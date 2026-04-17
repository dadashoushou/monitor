# OpenMonitor

网站内容监控抓取工具 + Web 管理界面

## 功能

- 添加/编辑/删除监控网站
- RSS 自动检测（扫描 `<link>`、`<a>` 标签及常见路径）
- 多种抓取模式：auto / html / js（动态渲染）/ stealth（隐蔽抓取）
- AI 智能分析：调用 LLM 自动生成 CSS 选择器规则，无需手动适配每个站点
- 定时抓取 + 手动抓取（单个/全部）
- 抓取历史查看，支持展开文章列表
- 实时进度条

## 技术栈

- **后端**: Python 3.12 + Flask
- **抓取引擎**: [Scrapling](https://github.com/D4Vinci/Scrapling)（Fetcher / DynamicFetcher / StealthyFetcher）
- **RSS 解析**: feedparser
- **AI 分析**: 支持任何 OpenAI 兼容 API（OpenAI / DeepSeek / Ollama 等）
- **前端**: 单文件 Jinja2 模板，无框架依赖
- **数据存储**: JSON 文件（sites.json / config.json / data/）

## 快速启动

```bash
pip install flask requests feedparser apscheduler scrapling
python app.py
```

浏览器打开 http://localhost:5000

## 配置

编辑项目根目录下的 `config.json`：

```json
{
  "crawl_interval_hours": 6,
  "data_dir": "",
  "ai": {
    "api_url": "https://api.deepseek.com/v1",
    "api_key": "sk-xxx",
    "model": "deepseek-chat"
  }
}
```

| 字段 | 说明 |
|------|------|
| `crawl_interval_hours` | 定时抓取间隔（小时） |
| `data_dir` | 抓取结果保存目录，空则使用默认 `./data` |
| `ai.api_url` | LLM API 地址（OpenAI 兼容接口） |
| `ai.api_key` | API 密钥 |
| `ai.model` | 模型名称 |

## AI 智能分析

对于新站点，点击「AI分析」按钮即可自动生成抓取规则：

1. 后端抓取目标页面 HTML
2. 去除 script/style/注释，截取前 30KB
3. 调用 LLM 分析页面结构，生成 CSS 选择器 + URL 过滤 + 时间提取规则
4. 规则缓存到 `sites.json`，后续抓取直接使用，零 AI 开销

未配置 AI 或未分析的站点自动降级到内置规则，不影响基本功能。

## 项目结构

```
├── app.py              # Flask 主应用 + API 路由
├── crawler.py          # 抓取引擎（RSS / HTML / JS / Stealth）
├── ai_analyzer.py      # AI 页面结构分析器
├── config.json         # 运行配置
├── sites.json          # 监控站点列表
├── templates/
│   └── index.html      # 前端页面
├── tests/
│   └── test_crawler.py # 单元测试
└── data/               # 抓取结果 JSON 文件
```

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | `/api/sites` | 站点 CRUD |
| PUT/DELETE | `/api/sites/<id>` | 更新/删除站点 |
| POST | `/api/check` | 检测所有站点 RSS |
| POST | `/api/crawl` | 抓取所有站点 |
| POST | `/api/crawl/<id>` | 抓取单个站点 |
| POST | `/api/sites/<id>/analyze` | AI 分析站点结构 |
| GET/POST | `/api/config` | 配置管理 |
| GET | `/api/results/<id>` | 查看抓取历史 |
