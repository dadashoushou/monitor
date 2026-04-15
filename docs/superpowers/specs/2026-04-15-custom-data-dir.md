# 自定义 JSON 输出路径设计文档

## 目标

允许用户在网页上配置抓取结果 JSON 文件的输出目录，支持绝对路径，持久化到 `config.json`。

## 架构

### config.json 新增字段

```json
{
  "crawl_interval_hours": 6,
  "data_dir": ""
}
```

- `data_dir` 为空字符串时，使用默认路径 `<项目根目录>/data/`
- `data_dir` 非空时，使用用户指定的绝对路径

### app.py 变更

1. `load_config()` 不变
2. 新增 `get_data_dir() -> Path`：读取 config 中的 `data_dir`，空则返回默认路径
3. `DATA_DIR` 模块级常量删除，改为每次调用 `get_data_dir()`
4. `POST /api/config` 支持 `data_dir` 字段：
   - 收到后尝试 `Path(data_dir).mkdir(parents=True, exist_ok=True)` 验证路径可写
   - 失败返回 `400 {"error": "路径无效或无权限"}`
   - 成功则保存到 config.json

### crawler.py 变更

- `DATA_DIR` 模块级常量删除
- `crawl_site(site, data_dir: Path)` 新增参数
- `crawl_all(sites, data_dir: Path)` 新增参数
- `app.py` 调用时传入 `get_data_dir()`

### index.html 变更

在 header 工具栏的 `#intervalSelect` 之后添加：

```html
<input id="dataDirInput" type="text" placeholder="数据目录（绝对路径，空=默认）" style="...">
<button id="btnSaveDataDir" class="btn btn-secondary">保存路径</button>
```

- 页面加载时调用 `GET /api/config` 填充当前值
- 点击"保存路径"调用 `POST /api/config { data_dir: ... }`
- 成功：按钮文字短暂变为"已保存 ✓"，边框变绿
- 失败：按钮文字短暂变为"路径无效"，边框变红

## 接口变更

`POST /api/config` 新增支持字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `data_dir` | string | 绝对路径，空字符串=恢复默认 |

响应：更新后的完整 config 对象，或 `400 {"error": "..."}` 

## 安全

- 路径不做白名单限制（用户自己的机器，自己负责）
- 后端只做 mkdir 可写性验证，不做路径遍历防护（本地工具，非公网）
