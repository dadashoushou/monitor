# OpenMonitor 部署指南

本文档覆盖 `openmonitor/` 主服务的依赖安装、配置说明和启动方式。

## 1. 运行环境

- Python 3.12
- Windows / Linux / macOS 任一可运行 Python 的环境
- 能访问目标站点的网络
- 可选：OpenAI 兼容接口，用于 AI 生成抓取选择器

说明：

- 仅使用 RSS / HTML 抓取模式时，安装 Python 依赖即可。
- 使用 `js` / `stealth` 模式时，`scrapling` 可能还需要额外的浏览器运行环境；如果动态抓取失败，先检查 Scrapling 的浏览器依赖是否已经安装完成。

## 2. 安装依赖

在 `openmonitor/` 目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. 配置文件

将 `config.example.json` 复制为 `config.json`：

```powershell
Copy-Item config.example.json config.json
```

默认示例：

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

字段说明：

- `crawl_interval_hours`：定时全站抓取间隔，单位小时。
- `data_dir`：抓取结果输出目录。留空时默认写入 `openmonitor/data/`。
- `mirror_data_dir`：标题索引去重目录。留空时默认写入 `openmonitor/history_mirror/`。
- `max_items`：单站点单次最多保留的文章数。
- `max_article_age_days`：按文章发布时间过滤旧内容。`0` 表示不过滤。
- `ai.api_url`：OpenAI 兼容接口地址。
- `ai.api_key`：AI 服务密钥。
- `ai.model`：用于生成选择器规则的模型名。

## 4. 数据文件和目录

服务运行时会读取或生成以下内容：

- `config.json`：运行配置。
- `sites.json`：站点列表。文件不存在时，应用会以空列表启动，也可以通过页面直接新增站点。
- `data/` 或自定义 `data_dir`：抓取结果快照。
- `history_mirror/` 或自定义 `mirror_data_dir`：每个站点的标题索引和去重状态。

如果希望手工初始化站点列表，可以新建：

```json
[]
```

## 5. 启动服务

在 `openmonitor/` 目录执行：

```powershell
python app.py
```

默认访问地址：

- `http://127.0.0.1:5000`

启动后建议先做三件事：

1. 打开页面确认站点列表接口可访问。
2. 在“运行配置”里确认 `data_dir` / `mirror_data_dir` 是否符合预期。
3. 新增一个测试站点，先执行 RSS 检测，再执行单站抓取。

## 6. 首次部署建议

- `config.json`、`sites.json`、`data/`、`history_mirror/` 都属于本地运行数据，不要提交到公共仓库。
- 如果只是本地或内网使用，直接 `python app.py` 即可。
- 如果需要长期运行，建议挂到进程管理器下，例如 NSSM、systemd、Supervisor 或容器入口。
- 当前 `app.py` 默认用 Flask 自带开发服务器启动，适合内部工具和测试环境；正式生产前建议改为非调试模式并置于受控进程管理下。

## 7. 常见问题

### 抓取结果没有落盘

先检查：

- `config.json` 里的 `data_dir` 是否存在且有写权限。
- 站点是否先完成了 RSS 检测或单站抓取。
- 目标站点是否返回了可识别的文章列表。

### `js` / `stealth` 模式抓取为空

优先排查：

- 运行机是否具备 Scrapling 所需浏览器依赖。
- 目标站点是否有更强的反爬策略。
- 是否可以先切回 `html` 模式验证基础链路。

### AI 分析返回失败

检查：

- `config.json` 中 `ai.api_url`、`ai.api_key`、`ai.model` 是否完整。
- `api_url` 是否可直接访问 `/v1/chat/completions`。
- 当前模型是否支持标准 Chat Completions 请求格式。
