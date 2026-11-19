/**
 * 编辑型工作台三栏布局（DESIGN.md §5）：
 * 顶栏 56px；左栏 260px（可折叠）、中栏 max-width 720px 居中、右栏 300px。
 * 层次靠 1px 描边与留白承担，无阴影、无渐变、无面性图标。
 * 历史问答收起侧栏列表，统一由顶栏右上「历史」按钮弹出抽屉查看（会话 4）。
 */
import { useState } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { MainPanel } from "./components/MainPanel";
import { VideoPanel } from "./components/VideoPanel";
import { HistoryDrawer } from "./components/HistoryDrawer";
import { Icon } from "./components/Icon";
import { useWorkbench } from "./hooks/useWorkbench";
import type { VideoTask } from "./types";

const EXAMPLE_QUESTIONS = [
  "众赢科技 2025 年研发投入占营收比重是多少？",
  "澎湃教育的主营业务有哪些？",
  "未来在线的信息技术服务面向哪些行业？",
];

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [uploading, setUploading] = useState(false);
  const wb = useWorkbench();

  const activeVideoTaskId = wb.activeVideoTaskId;
  const sortedTasks: VideoTask[] = [...wb.videoTasks].sort((a, b) => {
    const rank = (t: VideoTask) => (t.status === "running" ? 0 : t.status === "queued" ? 1 : 2);
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    return b.id - a.id;
  });

  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundColor: "var(--nb-bg)",
        color: "var(--nb-text)",
        fontFamily: "var(--font-family-sans)",
        display: "flex",
        flexDirection: "column",
      }}
    >
      <TopBar
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen((v) => !v)}
        onCreate={() => wb.ask(EXAMPLE_QUESTIONS[0] ?? "")}
        onOpenHistory={() => wb.setHistoryOpen(true)}
      />

      {wb.askWarning ? (
        <div
          role="note"
          className="flex items-center"
          style={{
            gap: "var(--space-8)",
            padding: "var(--space-8) var(--space-16)",
            backgroundColor: "var(--nb-bg-subtle)",
            borderBottom: "var(--border-width) solid var(--nb-border)",
            fontSize: "var(--text-meta-size)",
            color: "var(--nb-text-tertiary)",
          }}
        >
          <Icon name="quote" size={16} />
          <span>{wb.askWarning}</span>
        </div>
      ) : null}

      {wb.error ? (
        <div
          role="alert"
          className="flex items-center justify-between"
          style={{
            padding: "var(--space-8) var(--space-16)",
            backgroundColor: "var(--nb-tint-amber-bg)",
            color: "var(--nb-tint-amber-ink)",
            borderBottom: "var(--border-width) solid var(--nb-border)",
            fontSize: "var(--text-body-size)",
          }}
        >
          <span>{wb.error}</span>
          <button
            type="button"
            aria-label="关闭错误提示"
            className="flex items-center justify-center rounded-full"
            style={{ width: 28, height: 28 }}
            onClick={wb.clearError}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      ) : null}

      <div className="flex min-h-0 flex-1" style={{ height: "calc(100vh - 56px)" }}>
        {/* 左栏 260px：文档库（历史问答已迁至顶栏抽屉） */}
        <aside
          style={{
            width: sidebarOpen ? 260 : 0,
            minWidth: sidebarOpen ? 260 : 0,
            overflow: "hidden",
            transition: "width var(--duration-normal) var(--ease-out)",
            backgroundColor: "var(--nb-bg-subtle)",
            borderRight: sidebarOpen ? "var(--border-width) solid var(--nb-border)" : "none",
          }}
        >
          <div style={{ width: 260, height: "100%", padding: "var(--space-16)" }}>
            <Sidebar
              documents={wb.documents}
              selectedDocIds={wb.selectedDocIds}
              onToggleDoc={wb.toggleDocSelection}
              onToggleAllDocs={wb.toggleAllDocs}
              onUpload={async (f) => {
                setUploading(true);
                try {
                  await wb.upload(f);
                } finally {
                  setUploading(false);
                }
              }}
              onDeleteDoc={wb.removeDocument}
              uploading={uploading}
            />
          </div>
        </aside>

        {/* 中栏：问答主区，max-width 720px 居中 */}
        <main
          className="flex min-w-0 flex-1 items-start justify-center overflow-y-auto"
          style={{ padding: "var(--space-24)" }}
        >
          <MainPanel
            question={wb.currentQuestion}
            answer={wb.answer}
            citations={wb.citations}
            riskWarnings={wb.riskWarnings}
            noDocSelected={wb.documents.length > 0 && wb.selectedDocIds.length === 0}
            progress={wb.progress}
            isAsking={wb.isAsking}
            refusalReason={wb.refusalReason}
            confidence={wb.confidence}
            error={null}
            onAsk={wb.ask}
            examples={EXAMPLE_QUESTIONS}
          />
        </main>

        {/* 右栏 300px：视频工作室 */}
        <aside
          style={{
            width: 300,
            minWidth: 300,
            backgroundColor: "var(--nb-bg-subtle)",
            borderLeft: "var(--border-width) solid var(--nb-border)",
            padding: "var(--space-16)",
          }}
        >
          <div
            style={{
              fontSize: "var(--text-section-title-size)",
              lineHeight: "var(--text-section-title-line-height)",
              fontWeight: "var(--text-section-title-weight)",
              color: "var(--nb-text)",
              marginBottom: "var(--space-8)",
            }}
          >
            视频工作室
          </div>
          <VideoPanel
            tasks={sortedTasks}
            runningCount={wb.runningCount}
            activeTaskId={activeVideoTaskId}
            onDeleteTask={wb.removeVideoTask}
            onPlayTask={wb.playVideoTask}
          />
        </aside>
      </div>

      {/* 历史问答抽屉（右上角按钮触发） */}
      <HistoryDrawer
        open={wb.historyOpen}
        records={wb.qaRecords}
        selectedId={wb.selectedHistoryId}
        onSelect={wb.selectHistory}
        onDelete={wb.removeHistory}
        onClose={() => wb.setHistoryOpen(false)}
      />
    </div>
  );
}
