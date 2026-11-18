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
      },
      borderRadius: {
        sm: "var(--nb-radius-sm)",
        md: "var(--nb-radius-md)",
        lg: "var(--nb-radius-lg)",
        pill: "var(--nb-radius-pill)",
      },
      boxShadow: {
        float: "var(--shadow-float)",
        none: "var(--shadow-none)",
      },
    },
  },
  plugins: [],
};
