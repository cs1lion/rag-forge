# DESIGN.md — 编辑型工作台设计规范

> 本文件是设计令牌的**唯一事实来源（single source of truth）**。
> `design/tokens.css` 与 `design/tokens.json` 由 `scripts/gen_tokens.py` 从本文件
> 的 `tokens` 代码块生成，并由 `scripts/check_tokens.py` 做三方 100% 一致性校验。
> 任何视觉改动须先改本文件，再重新生成令牌。

## 1. 设计方向

知识库问答与自动问答视频生成工作台，定位为**编辑室（newsroom）气质**的生产力工具：

- **纸感**：暖米白底色、细腻分隔线、克制的投影，像摊开的稿纸而不是发光屏幕；
- **编辑秩序**：清晰的标题层级、充足的留白、段落级引用卡片，信息有"版面"感；
- **去 AI 味**：不用渐变紫蓝、不用玻璃拟态、不用霓虹辉光；色彩以松绿 + 灯芯琥珀
  + 陶土点缀为主，像编辑部里的旧台灯与绿皮笔记本；
- **可编辑感**：任务队列、文档列表像待办稿纸，进度条像排版校样上的墨线。

## 2. 色板（Color Palette）

### 2.1 基础色
| 令牌 | 值 | 用途 |
| --- | --- | --- |
| paper | `#F7F4EE` | 页面底色（暖米白） |
| surface | `#FDFCFA` | 卡片/面板底色 |
| surface-raised | `#FFFFFF` | 悬浮层底色 |
| ink | `#1A1B1E` | 主文字（深墨） |
| ink-soft | `#3E4348` | 次级文字 |
| ink-mute | `#6B7280` | 弱化文字 |
| line | `#E3DED3` | 分隔线/描边（暖灰） |
| line-strong | `#C9C2B2` | 强调描边 |

### 2.2 品牌色
| 令牌 | 值 | 用途 |
| --- | --- | --- |
| brand | `#2F5D50` | 主色：松绿（按钮、激活态、品牌标识） |
| brand-deep | `#24483E` | 主色加深（hover、按压） |
| brand-tint | `#E4EDE8` | 主色浅底（选中态、标签底） |
| amber | `#C98A2C` | 灯芯琥珀：关键强调、进度高亮 |
| terracotta | `#B4552D` | 陶土：点缀（视频/媒体相关） |

### 2.3 功能色
| 令牌 | 值 | 用途 |
| --- | --- | --- |
| success | `#3E7C59` | 成功/完成 |
| warning | `#B97A1F` | 警告/排队中 |
| danger | `#B3402E` | 失败/错误 |
| info | `#4A6D8C` | 信息/中性提示（低饱和蓝，避免 AI 感） |

### 2.4 语义色（派生映射）
| 令牌 | 映射 |
| --- | --- |
| text-primary | ink |
| text-secondary | ink-soft |
| text-tertiary | ink-mute |
| bg-base | paper |
| bg-panel | surface |
| bg-elevated | surface-raised |
| border-subtle | line |
| border-strong | line-strong |
| interactive | brand |
| interactive-hover | brand-deep |
| interactive-bg | brand-tint |
| accent-highlight | amber |
| accent-media | terracotta |

## 3. 字体层级（Type Scale）

字体族：标题用衬线 `Noto Serif SC`（编辑感），正文用无衬线 `Noto Sans SC`，
等宽用 `JetBrains Mono`（数据/编号）。

| 令牌 | 字号 px | 行高 | 字重 | 字体族 | 用途 |
| --- | --- | --- | --- | --- | --- |
| display | 32 | 40 | 700 | serif | 工作台大标题 |
| h1 | 28 | 36 | 700 | serif | 页面主标题 |
| h2 | 22 | 30 | 600 | serif | 面板标题 |
| h3 | 18 | 26 | 600 | sans | 小节标题 |
| h4 | 16 | 24 | 600 | sans | 卡片标题 |
| body | 15 | 24 | 400 | sans | 正文 |
| small | 13 | 20 | 400 | sans | 辅助说明 |
| caption | 12 | 18 | 500 | sans | 标签/角标 |
| mono | 13 | 20 | 400 | mono | 编号/数据/代码 |

## 4. 间距基数（Spacing）

基数 4px，缩放序列：

| 令牌 | 值 px |
| --- | --- |
| space-1 | 4 |
| space-2 | 8 |
| space-3 | 12 |
| space-4 | 16 |
| space-5 | 20 |
| space-6 | 24 |
| space-8 | 32 |
| space-10 | 40 |
| space-12 | 48 |
| space-16 | 64 |

## 5. 圆角（Radius）

| 令牌 | 值 px | 用途 |
| --- | --- | --- |
| radius-sm | 4 | 小标签/输入框内元素 |
| radius-md | 8 | 按钮/输入框 |
| radius-lg | 12 | 卡片 |
| radius-xl | 16 | 大面板/模态 |
| radius-pill | 999 | 徽章/进度条 |

## 6. 阴影（Elevation）

| 令牌 | 值 |
| --- | --- |
| shadow-sm | `0 1px 2px rgba(26,27,30,0.06)` |
| shadow-md | `0 4px 12px rgba(26,27,30,0.08)` |
| shadow-lg | `0 12px 32px rgba(26,27,30,0.12)` |

## 7. 动效（Motion）

| 令牌 | 值 |
| --- | --- |
| duration-fast | 120ms |
| duration-normal | 240ms |
| duration-slow | 400ms |
| ease-out | `cubic-bezier(0.22, 1, 0.36, 1)` |
| ease-in-out | `cubic-bezier(0.65, 0, 0.35, 1)` |

## 8. 布局原则

- 三栏工作台：左栏文档库（240px）｜中栏问答与引用（弹性）｜右栏任务队列与历史（320px）；
- 引用卡片带 `para_id` 定位锚点，点击定位到原文段落；
- 视频进度用 `amber` 墨线 + `pill` 圆角进度条，排队态用 `warning`。

---

## 9. 机器可解析令牌块（source of truth）

> `scripts/gen_tokens.py` 只读取本代码块生成 `design/tokens.css` 与 `design/tokens.json`。

```tokens
{
  "color": {
    "paper": "#F7F4EE",
    "surface": "#FDFCFA",
    "surface-raised": "#FFFFFF",
    "ink": "#1A1B1E",
    "ink-soft": "#3E4348",
    "ink-mute": "#6B7280",
    "line": "#E3DED3",
    "line-strong": "#C9C2B2",
    "brand": "#2F5D50",
    "brand-deep": "#24483E",
    "brand-tint": "#E4EDE8",
    "amber": "#C98A2C",
    "terracotta": "#B4552D",
    "success": "#3E7C59",
    "warning": "#B97A1F",
    "danger": "#B3402E",
    "info": "#4A6D8C"
  },
  "semantic": {
    "text-primary": "color.ink",
    "text-secondary": "color.ink-soft",
    "text-tertiary": "color.ink-mute",
    "bg-base": "color.paper",
    "bg-panel": "color.surface",
    "bg-elevated": "color.surface-raised",
    "border-subtle": "color.line",
    "border-strong": "color.line-strong",
    "interactive": "color.brand",
    "interactive-hover": "color.brand-deep",
    "interactive-bg": "color.brand-tint",
    "accent-highlight": "color.amber",
    "accent-media": "color.terracotta"
  },
  "font": {
    "family-serif": "'Noto Serif SC', Georgia, serif",
    "family-sans": "'Noto Sans SC', system-ui, sans-serif",
    "family-mono": "'JetBrains Mono', 'SFMono-Regular', monospace"
  },
  "type": {
    "display": { "size": 32, "line-height": 40, "weight": 700, "family": "font.family-serif" },
    "h1": { "size": 28, "line-height": 36, "weight": 700, "family": "font.family-serif" },
    "h2": { "size": 22, "line-height": 30, "weight": 600, "family": "font.family-serif" },
    "h3": { "size": 18, "line-height": 26, "weight": 600, "family": "font.family-sans" },
    "h4": { "size": 16, "line-height": 24, "weight": 600, "family": "font.family-sans" },
    "body": { "size": 15, "line-height": 24, "weight": 400, "family": "font.family-sans" },
    "small": { "size": 13, "line-height": 20, "weight": 400, "family": "font.family-sans" },
    "caption": { "size": 12, "line-height": 18, "weight": 500, "family": "font.family-sans" },
    "mono": { "size": 13, "line-height": 20, "weight": 400, "family": "font.family-mono" }
  },
  "spacing": {
    "space-1": 4, "space-2": 8, "space-3": 12, "space-4": 16,
    "space-5": 20, "space-6": 24, "space-8": 32, "space-10": 40,
    "space-12": 48, "space-16": 64
  },
  "radius": {
    "radius-sm": 4, "radius-md": 8, "radius-lg": 12, "radius-xl": 16, "radius-pill": 999
  },
  "shadow": {
    "shadow-sm": "0 1px 2px rgba(26,27,30,0.06)",
    "shadow-md": "0 4px 12px rgba(26,27,30,0.08)",
    "shadow-lg": "0 12px 32px rgba(26,27,30,0.12)"
  },
  "motion": {
    "duration-fast": "120ms",
    "duration-normal": "240ms",
    "duration-slow": "400ms",
    "ease-out": "cubic-bezier(0.22, 1, 0.36, 1)",
    "ease-in-out": "cubic-bezier(0.65, 0, 0.35, 1)"
  }
}
```
