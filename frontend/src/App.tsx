/**
 * 会话 1 基线骨架：验证设计令牌经 CSS 自定义属性生效。
 * 编辑型工作台三栏布局（文档库 / 问答与引用 / 任务队列）在后续会话实现，
 * 视觉规范以 DESIGN.md 与 design/tokens.css 为唯一来源。
 *
 * 设计方向（DESIGN.md v2，NotebookLM 参考系）：
 * 白底、细线分区、克制圆角、极低饱和表面层次；彩色只出现在功能图标与少量链接；
 * 层次靠线和留白，不靠阴影和色块堆叠。
 */
export default function App() {
  return (
    <div
      style={{
        backgroundColor: "var(--nb-bg)",
        color: "var(--nb-text)",
        fontFamily: "var(--font-family-sans)",
        minHeight: "100vh",
        padding: "var(--space-24)",
      }}
    >
      <header style={{ borderBottom: "var(--border-width) solid var(--nb-border)", paddingBottom: "var(--space-16)" }}>
        <h1
          style={{
            fontSize: "var(--text-page-title-size)",
            lineHeight: "var(--text-page-title-line-height)",
            fontWeight: "var(--text-page-title-weight)",
          }}
        >
          知识库问答与视频工作台
        </h1>
        <p style={{ color: "var(--nb-text-secondary)", fontSize: "var(--text-body-size)" }}>
          会话 1 基线：设计令牌生效验证（白底 · 细线分区 · 强调蓝 #1A73E8）
        </p>
      </header>

      <main
        style={{
          display: "grid",
          gridTemplateColumns: "260px minmax(0, 720px) 300px",
          gap: "var(--space-24)",
          marginTop: "var(--space-24)",
          justifyContent: "center",
        }}
      >
        {["文档库", "问答与引用", "任务队列与历史"].map((title, i) => (
          <section
            key={title}
            style={{
              backgroundColor: "var(--nb-bg)",
              border: "var(--border-width) solid var(--nb-border)",
              borderRadius: "var(--nb-radius-md)",
              padding: "var(--space-16)",
            }}
          >
            <h2
              style={{
                fontSize: "var(--text-section-title-size)",
                lineHeight: "var(--text-section-title-line-height)",
                fontWeight: "var(--text-section-title-weight)",
              }}
            >
              {title}
            </h2>
            <p style={{ color: "var(--nb-text-tertiary)", fontSize: "var(--text-meta-size)", marginTop: "var(--space-8)" }}>
              {i === 0 ? "上传 .md / .docx / .doc" : i === 1 ? "提问 · 回答 · 引用溯源" : "视频队列（单并发 FIFO）"}
            </p>
            <div
              style={{
                marginTop: "var(--space-16)",
                height: "var(--space-4)",
                borderRadius: "var(--nb-radius-pill)",
                backgroundColor: "var(--nb-bg-hover)",
              }}
            />
            <div
              style={{
                marginTop: "var(--space-8)",
                height: "var(--space-4)",
                width: "60%",
                borderRadius: "var(--nb-radius-pill)",
                backgroundColor: "var(--nb-accent-soft)",
              }}
            />
          </section>
        ))}
      </main>
    </div>
  );
}
