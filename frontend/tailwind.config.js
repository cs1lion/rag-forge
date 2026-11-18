/** @type {import('tailwindcss').Config} */
// 设计令牌唯一来源是 design/tokens.css（由 DESIGN.md 生成）；
// Tailwind 只消费令牌对应的语义色名，不在本文件重复硬编码色值。
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        serif: ["var(--font-family-serif)", "serif"],
        sans: ["var(--font-family-sans)", "sans-serif"],
        mono: ["var(--font-family-mono)", "monospace"],
      },
    },
  },
  plugins: [],
};
