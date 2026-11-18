/**
 * 会话 1 基线骨架：验证设计令牌经 CSS 自定义属性生效。
 * 编辑型工作台三栏布局（文档库 / 问答 / 任务队列）在后续会话实现，
 * 视觉规范以 DESIGN.md 与 design/tokens.css 为唯一来源。
 */
export default function App() {
  return (
    <div
      style={{
        backgroundColor: "var(--bg-base)",
        color: "var(--text-primary)",
        fontFamily: "var(--font-family-sans)",
        minHeight: "100vh",
        padding: "var(--space-8)",
      }}
    >
      <header>
        <h1
          style={{
            fontFamily: "var(--font-family-serif)",
            fontSize: "var(--text-h1-size)",
            fontWeight: "var(--text-h1-weight)",
            lineHeight: "var(--text-h1-line-height)",
          }}
        >
          知识库问答与视频工作台
        </h1>
        <p style={{ color: "var(--text-secondary)" }}>
          会话 1 基线：设计令牌生效验证（松绿 · 灯芯琥珀 · 纸感底色）
        </p>
      </header>

      <main
        style={{
          display: "grid",
          gridTemplateColumns: "240px 1fr 320px",
          gap: "var(--space-6)",
          marginTop: "var(--space-6)",
        }}
      >
        {["文档库", "问答与引用", "任务队列与历史"].map((title, i) => (
          <section
            key={title}
            style={{
              backgroundColor: "var(--bg-panel)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--space-6)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <h2
              style={{
                fontFamily: "var(--font-family-serif)",
                fontSize: "var(--text-h2-size)",
                fontWeight: "var(--text-h2-weight)",
              }}
            >
              {title}
            </h2>
            <p style={{ color: "var(--text-tertiary)", marginTop: "var(--space-3)" }}>
              {i === 0 ? "上传 .md / .docx / .doc" : i === 1 ? "提问 · 回答 · 引用溯源" : "视频队列（单并发 FIFO）"}
            </p>
            <div
              style={{
                marginTop: "var(--space-4)",
                height: "var(--space-2)",
                borderRadius: "var(--radius-pill)",
                backgroundColor: "var(--interactive-bg)",
              }}
            />
          </section>
        ))}
      </main>
    </div>
  );
}
