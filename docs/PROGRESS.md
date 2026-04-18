# OpenMonitor — 实施进度追踪

> 用于断点恢复。每完成一步更新状态，下次对话时从第一个 `[ ]` 继续。

---

## 文档阶段

- [x] PRD 企划书 (`docs/PRD.md`)
- [x] 设计规范 (`docs/DESIGN_SPEC.md`)
- [x] 视觉设计稿 (`design/mockup.html`)
- [x] 进度追踪文档 (`docs/PROGRESS.md`)

## 实施阶段

### P0: crawler.py 重写 ✅

- [x] 安装 scrapling 依赖
- [x] 新增 `_extract_articles(page, site_url, selectors)` 公共提取函数
- [x] 用 Scrapling Fetcher 重写 `crawl_html()`
- [x] 新增 `crawl_js()` — DynamicFetcher
- [x] 新增 `crawl_stealth()` — StealthyFetcher
- [x] 修改 `crawl_site()` 路由逻辑（支持 crawl_mode 决策树）
- [x] 修改 `crawl_all()` 并发策略（静态 5 并发，动态 2 并发）
- [x] 单元测试验证（24 个测试全部通过）

### P1-a: app.py 适配 ✅

- [x] `add_site()` 接收并存储 `crawl_mode` 字段，默认 `"auto"`
- [x] `update_site()` 支持修改 `crawl_mode`
- [x] 向后兼容（已有站点无字段时默认 auto）

### P1-b: templates/index.html 前端更新 ✅

- [x] 新增 `.badge-auto`、`.badge-html`、`.badge-js`、`.badge-stealth` CSS
- [x] 添加/编辑弹窗：新增"抓取模式"下拉选择器
- [x] `saveSite()` 提交 `crawl_mode` 字段
- [x] `openModal()` 编辑时回填 `crawl_mode`
- [x] `renderTable()` 新增"抓取模式"列

### P2: AI 智能分析 ✅

- [x] 新增 `ai_analyzer.py` — 调用 LLM 分析页面结构，生成 CSS 选择器规则
- [x] `_extract_articles()` 支持 selectors 参数（css_selector / url_pattern / time_css / time_url）
- [x] 新增 `/api/sites/<id>/analyze` 端点
- [x] 前端 AI 分析按钮 + selectors 预览
- [x] AI 设置从页面移至 `config.json` 配置文件
- [x] 规则缓存到 sites.json，后续抓取零 AI 开销
- [x] 5 个 selectors 路径测试全部通过

### P3: 工程优化 ✅

- [x] Scrapling 改用类方法调用，消除 deprecated 警告
- [x] AI API 超时调整（120s）
- [x] README.md 完整更新（功能、技术栈、配置、API、项目结构）
- [x] 敏感文件（config.json / sites.json）从 git 追踪移除
- [x] 新增 config.example.json 配置模板
- [x] 13 个 commit 待推送到 GitHub（`git push origin main`）

---

## 待办：下一轮迭代

### P4: 抓取质量提升

- [ ] AI 分析失败时的重试机制（指数退避）
- [ ] selectors 规则有效性校验（分析后试抓，0 结果则重新分析）
- [ ] 支持分页抓取（翻页 / 加载更多）
- [ ] 文章去重（URL 指纹）
- [ ] 增量抓取（只保存新文章）

### P5: 前端体验

- [ ] AI 分析进度提示（loading 动画 + 预计耗时）
- [ ] selectors 规则手动编辑 / 微调界面
- [ ] 抓取结果预览优化（表格展示、时间排序）
- [ ] 站点分组 / 标签管理
- [ ] 深色模式

### P6: 稳定性 & 运维

- [ ] 日志系统（文件 + 级别控制）
- [ ] 抓取失败告警（连续 N 次失败通知）
- [ ] 健康检查端点 `/api/health`
- [ ] Docker 部署支持
- [ ] 数据备份 / 导出

### P7: 高级功能

- [ ] 内容摘要（AI 生成文章摘要）
- [ ] 关键词监控 + 告警推送（邮件 / Webhook）
- [ ] 多用户支持
- [ ] API 鉴权

---

## 当前状态

**最后更新**: 2025-07-18
**已完成**: P0 ~ P3（基础抓取 + AI 分析 + 工程优化）
**下一步**: P4（抓取质量提升）或根据需求优先级调整

## 如何恢复

下次对话时告诉我：**"继续实施"** 或 **"从断点继续"**

我会读取这个文件，找到第一个未完成的 `[ ]` 项，从那里继续。
