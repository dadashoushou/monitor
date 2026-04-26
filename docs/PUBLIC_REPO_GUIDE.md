# OpenMonitor 公开仓库说明

本仓库用于保存可公开共享的源码、测试和设计文档。

以下内容属于本地运行状态或敏感配置，不应提交到 GitHub：
- `config.json`
- `sites.json`
- `state.json`
- `data/`
- `raw/`
- `mirror-data/`
- `history_mirror/`
- `graphify-out/`
- `.graphify_*`
- `.pytest_cache/`
- 各类 `__pycache__/`

## 首次配置

1. 复制 `config.example.json` 为 `config.json`
2. 填入你自己的 API 地址、密钥、模型名和数据目录
3. 根据需要新建 `sites.json`，或通过页面初始化站点配置

## 提交前检查

1. 确认 `git status` 中没有 `config.json`、`sites.json`、`data/`、`mirror-data/`、`history_mirror/`、缓存目录或图谱产物
2. 确认文档中的示例值使用占位符，而不是真实 URL、密钥或本地路径
3. 确认抓取数据、临时状态和测试缓存都留在本地

## 文档约定

- README 只描述公开可复现的使用方式
- 示例配置统一使用占位符，不放真实 URL、Key 或本地路径
- 设计或数据流文档中的路径示例优先使用 `./data` 或 `<your-data-dir>`
