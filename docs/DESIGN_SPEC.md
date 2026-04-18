# OpenMonitor — UI 设计规范

> 版本: v1.0 | 日期: 2026-04-17 | 配套设计稿: `design/mockup.html`

---

## 1. 设计方向

延续现有 UI 的 **工具型极简** 风格：白底、黑色主按钮、语义化 pill badge、系统字体。
新增元素不引入额外视觉复杂度，通过配色和微标记（圆点前缀）与现有元素区分。

## 2. 配色系统

### 2.1 基础色（不变）

| 用途 | 变量 | 色值 |
|------|------|------|
| 页面背景 | `--bg` | `#f5f5f5` |
| 卡片/表面 | `--surface` | `#ffffff` |
| 边框 | `--border` | `#e5e5e5` |
| 主文字 | `--text` | `#1a1a1a` |
| 次要文字 | `--text-muted` | `#666666` |
| 弱化文字 | `--text-dim` | `#999999` |
| 主按钮 | `--primary` | `#1a1a1a` |

### 2.2 状态 Badge 色（不变）

| 状态 | 背景 | 前景 |
|------|------|------|
| RSS | `#dcfce7` | `#16a34a` |
| 无RSS | `#fef9c3` | `#a16207` |
| 待检测 | `#f3f4f6` | `#6b7280` |
| 超时/出错 | `#fee2e2` | `#dc2626` |
| 检测中 | `#dbeafe` | `#2563eb` |

### 2.3 模式 Badge 色（新增）

| 模式 | 背景 | 前景 | 设计意图 |
|------|------|------|----------|
| auto | `#f3f4f6` | `#6b7280` | 中性灰，默认态不抢视觉 |
| html | `#dbeafe` | `#2563eb` | 蓝色，静态可靠 |
| js | `#ede9fe` | `#7c3aed` | 紫色，动态渲染的复杂度 |
| stealth | `#ffedd5` | `#c2410c` | 橙色，高级/隐蔽操作 |

配色逻辑：四种模式按"复杂度递增"排列，色温从冷（灰→蓝）到暖（紫→橙），直觉上传达操作的"重量感"。

## 3. Badge 规范

### 3.1 通用样式

```css
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 99px;      /* pill 形状 */
  font-size: 11px;
  font-weight: 500;
}
```

### 3.2 模式 Badge（新增）

模式 badge 在文字前增加 6px 圆点指示器，与状态 badge 形成视觉区分：

```css
.badge-auto    { background: #f3f4f6; color: #6b7280; }
.badge-html    { background: #dbeafe; color: #2563eb; }
.badge-js      { background: #ede9fe; color: #7c3aed; }
.badge-stealth { background: #ffedd5; color: #c2410c; }
```

HTML 结构：
```html
<span class="badge badge-js">JS</span>
```

### 3.3 区分规则

| 类型 | 示例 | 用途 |
|------|------|------|
| 状态 badge | `RSS` `无RSS` `待检测` | 表示 RSS 检测结果 |
| 模式 badge | `AUTO` `HTML` `JS` `STEALTH` | 表示用户选择的抓取模式 |

两类 badge 可在同一行出现（表格中状态列和模式列相邻），通过颜色体系自然区分。

## 4. 表格变更

### 4.1 列顺序

```
名称 | URL | RSS 地址 | 状态 | 抓取模式(新) | 最近条目数 | 上次抓取 | 操作
```

"抓取模式"列插入在"状态"之后，因为两者语义相关但维度不同：
- 状态 = 系统检测结果（被动）
- 模式 = 用户配置选择（主动）

### 4.2 模式列渲染

```javascript
// STATUS_LABEL 新增映射
const MODE_LABEL = {
  auto: 'AUTO',
  html: 'HTML',
  js: 'JS',
  stealth: 'STEALTH',
};

// 表格单元格
`<td><span class="badge badge-${mode}">${MODE_LABEL[mode]}</span></td>`
```

### 4.3 空状态

已有站点无 `crawl_mode` 字段时，前端读取默认显示 `AUTO` badge。

## 5. 弹窗变更

### 5.1 字段顺序

```
名称 *
URL *
抓取模式 (新增)
备注
```

"抓取模式"位于 URL 之后、备注之前，因为它是站点配置的核心属性。

### 5.2 选择器设计

使用原生 `<select>` 元素，保持与现有表单风格一致：

```html
<div class="field">
  <label>抓取模式</label>
  <select id="fCrawlMode">
    <option value="auto">auto — 自动（默认）</option>
    <option value="html">html — 静态抓取</option>
    <option value="js">js — 动态渲染</option>
    <option value="stealth">stealth — 隐蔽抓取</option>
  </select>
</div>
```

样式：
```css
.field select {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #d4d4d4;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  background: #fff;
  cursor: pointer;
}
.field select:focus { border-color: #1a1a1a; }
```

### 5.3 编辑回填

编辑已有站点时，`<select>` 回填当前 `crawl_mode` 值：
```javascript
document.getElementById('fCrawlMode').value = s.crawl_mode || 'auto';
```

## 6. 交互规范

### 6.1 模式切换

- 切换模式仅影响下次抓取，不触发立即抓取
- 切换后表格中的模式 badge 立即更新
- 无确认弹窗（低风险操作）

### 6.2 抓取反馈

- 单站点抓取：按钮文字变为"抓取中…"并 disabled
- 全部抓取：顶部进度条 + 轮询状态
- 动态模式（js/stealth）抓取耗时更长，无需额外提示（用户在选择模式时已知晓）

### 6.3 向后兼容

- 已有站点在 UI 中默认显示 AUTO badge
- 编辑已有站点时选择器默认选中 auto
- 不强制用户为已有站点设置模式

## 7. 响应式考虑

当前 UI 为桌面优先的管理工具，不做移动端适配。
新增列在窄屏下可能导致表格横向滚动，这是可接受的（管理工具的标准行为）。

## 8. 可访问性

- `<select>` 使用原生元素，天然支持键盘导航和屏幕阅读器
- Badge 使用语义化文字（AUTO/HTML/JS/STEALTH），不依赖颜色传达信息
- 所有新增颜色对比度满足 WCAG AA 标准（前景色在对应背景色上的对比度 ≥ 4.5:1）

## 9. 视觉参考

完整可交互设计稿：`design/mockup.html`（浏览器直接打开）

设计稿包含：
1. 配色色板
2. Badge 样本对比
3. 四种模式说明卡片
4. 表格完整 mockup（新增列高亮标注）
5. 弹窗前后对比
6. 下拉选择器展开态
7. CSS 实现代码
8. 数据流示意
9. 实施清单
