/** @type {import('tailwindcss').Config} */
// 设计令牌唯一来源是 design/tokens.css（由 DESIGN.md 生成）。
// Tailwind 只消费令牌对应的语义色名，不在本文件重复硬编码色值。
// 注意：DESIGN.md v2（NotebookLM 参考系）只有 --font-family-sans，无 serif。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-family-sans)", "sans-serif"],
        // DESIGN.md v2 未定义 mono 令牌；如需等宽数字可用 font-variant-numeric
        mono: ["var(--font-family-sans)", "monospace"],
      },
      colors: {
        // 语义映射到 CSS 自定义属性（值以 design/tokens.css 为准）
        base: "var(--nb-bg)",
        subtle: "var(--nb-bg-subtle)",
        hover: "var(--nb-bg-hover)",
        ink: "var(--nb-text)",
        "ink-secondary": "var(--nb-text-secondary)",
        "ink-tertiary": "var(--nb-text-tertiary)",
        accent: "var(--nb-accent)",
        "accent-hover": "var(--nb-accent-hover)",
        "accent-soft": "var(--nb-accent-soft)",
        // 功能色块（成对：底 + 墨，来源/状态图标使用，DESIGN.md §3）
        "tint-amber-bg": "var(--nb-tint-amber-bg)",
        "tint-amber-ink": "var(--nb-tint-amber-ink)",
        "tint-violet-bg": "var(--nb-tint-violet-bg)",
        "tint-violet-ink": "var(--nb-tint-violet-ink)",
        "tint-green-bg": "var(--nb-tint-green-bg)",
        "tint-green-ink": "var(--nb-tint-green-ink)",
        "tint-teal-bg": "var(--nb-tint-teal-bg)",
        "tint-teal-ink": "var(--nb-tint-teal-ink)",
        "tint-blue-bg": "var(--nb-tint-blue-bg)",
        "tint-blue-ink": "var(--nb-tint-blue-ink)",
      },
      borderRadius: {
        sm: "var(--nb-radius-sm)",
        md: "var(--nb-radius-md)",
        lg: "var(--nb-radius-lg)",
        pill: "var(--nb-radius-pill)",
      },
      fontSize: {
        page: ["var(--text-page-title-size)", { lineHeight: "var(--text-page-title-line-height)" }],
        section: ["var(--text-section-title-size)", { lineHeight: "var(--text-section-title-line-height)" }],
        card: ["var(--text-card-title-size)", { lineHeight: "var(--text-card-title-line-height)" }],
        body: ["var(--text-body-size)", { lineHeight: "var(--text-body-line-height)" }],
        meta: ["var(--text-meta-size)", { lineHeight: "var(--text-meta-line-height)" }],
        micro: ["var(--text-micro-label-size)", { lineHeight: "var(--text-micro-label-line-height)" }],
      },
      boxShadow: {
        float: "var(--shadow-float)",
        none: "var(--shadow-none)",
      },
    },
  },
  plugins: [],
};
