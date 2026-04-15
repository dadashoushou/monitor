# OpenMonitor

网站 RSS 监控工具 + Web 管理界面

## 快速启动

```bash
pip install flask requests feedparser beautifulsoup4
python app.py
```

浏览器打开 http://localhost:5000

## 功能

- 添加/编辑/删除监控网站
- 一键触发 RSS 检测（支持单个或全部）
- 实时进度条
- 检测结果持久化到 sites.json
