/**
 * 编辑型工作台三栏布局（DESIGN.md §5）：
 * 顶栏 56px；左栏 260px（可折叠）、中栏 max-width 720px 居中、右栏 300px。
 * 层次靠 1px 描边与留白承担，无阴影、无渐变、无面性图标。
 *
 * 工作室级体验打磨：
 * 1. 动态生成基于当前已入库文档的示例问题（淘汰已删除演示语料的硬编码提问）；
 * 2. 全局快捷键：Cmd/Ctrl+B 折叠文档栏、Cmd/Ctrl+H 呼出历史抽屉、Esc 关闭抽屉；
 * 3. 中栏接入 DESIGN.md 令牌原生 EvidenceXRay 证据透视面板；
 * 4. 右栏视频工作室顶部增加状态胶囊与活跃/排队任务一键协作式取消（POST /api/video-tasks/{id}/cancel）。
 */
import { useEffect, useMemo, useState } from "react";
import { TopBar } from "./components/TopBar";
import { Sidebar } from "./components/Sidebar";
import { MainPanel } from "./components/MainPanel";
import { VideoPanel } from "./components/VideoPanel";
import { HistoryDrawer } from "./components/HistoryDrawer";
import { EvidenceXRay } from "./components/EvidenceXRay";
import { Icon } from "./components/Icon";
import { useWorkbench } from "./hooks/useWorkbench";
import type { VideoTask } from "./types";

const FALLBACK_EXAMPLES = [
  "总结当前知识库中最关键的制度与核心指标",
  "对比已选文档中的主要约束条件与适用范围",
  "列出文档中涉及的风险提示、异常条款或边界要求",
];

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [cancellingId, setCancellingId] = useState<number | null>(null);
  const wb = useWorkbench();

  // 根据当前知识库文档动态生成示例问题，避免硬编码过期语料实体
  const exampleQuestions = useMemo(() => {
    if (!wb.documents.length) {
      return FALLBACK_EXAMPLES;
    }
    const first = wb.documents[0]?.title || wb.documents[0]?.source_file;
    const second = wb.documents[1]?.title || wb.documents[1]?.source_file;
    const list = [`请总结《${first}》的核心要点与关键数据`];
    if (second) {
      list.push(`对比《${first}》与《${second}》中的核心条款差异`);
    } else {
      list.push(`《${first}》中有哪些明确的数值标准或边界约束？`);
    }
    list.push("知识库中是否包含需要特别注意的风险提示或限制条件？");
    return list;
  }, [wb.documents]);

  // 工作室级全局快捷键（Cmd/Ctrl+B 折叠侧栏、Cmd/Ctrl+H 历史抽屉、Esc 关闭抽屉）
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        setSidebarOpen((v) => !v);
      } else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "h") {
        e.preventDefault();
        wb.setHistoryOpen(!wb.historyOpen);
      } else if (e.key === "Escape" && wb.historyOpen) {
        wb.setHistoryOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [wb.historyOpen, wb.setHistoryOpen]);

  const activeVideoTaskId = wb.activeVideoTaskId;
  const sortedTasks: VideoTask[] = [...wb.videoTasks].sort((a, b) => {
    const rank = (t: VideoTask) => (t.status === "running" ? 0 : t.status === "queued" ? 1 : 2);
    const r = rank(a) - rank(b);
    if (r !== 0) return r;
    return b.id - a.id;
  });

  const cancellableTask = sortedTasks.find(
    (t) => t.status === "running" || t.status === "queued"
  );

  const handleCancelActiveTask = async (taskId: number) => {
    setCancellingId(taskId);
    try {
      await fetch(`/api/video-tasks/${taskId}/cancel`, { method: "POST" });
    } finally {
      setCancellingId(null);
    }
  };

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
        onCreate={() => wb.ask(exampleQuestions[0] ?? "")}
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
        {/* 左栏 260px：文档库 */}
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

        {/* 中栏：问答主区 + 证据透视 X-Ray，max-width 720px 居中 */}
        <main
          className="flex min-w-0 flex-1 flex-col items-center overflow-y-auto"
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
            examples={exampleQuestions}
          />
          {wb.citations.length > 0 ? <EvidenceXRay citations={wb.citations} /> : null}
        </main>

        {/* 右栏 300px：视频工作室 + 状态胶囊与一键取消 */}
        <aside
          style={{
            width: 300,
            minWidth: 300,
            backgroundColor: "var(--nb-bg-subtle)",
            borderLeft: "var(--border-width) solid var(--nb-border)",
            padding: "var(--space-16)",
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            className="flex items-center justify-between"
            style={{ marginBottom: "var(--space-12)", gap: "var(--space-8)" }}
          >
            <div className="flex items-center" style={{ gap: "var(--space-8)" }}>
              <span
                style={{
                  fontSize: "var(--text-section-title-size)",
                  lineHeight: "var(--text-section-title-line-height)",
                  fontWeight: "var(--text-section-title-weight)",
                  color: "var(--nb-text)",
                }}
              >
                视频工作室
              </span>
              {wb.runningCount > 0 ? (
                <span
                  className="nb-pill"
                  style={{
                    backgroundColor: "var(--nb-tint-teal-bg)",
                    color: "var(--nb-tint-teal-ink)",
                  }}
                >
                  合成中
                </span>
              ) : null}
            </div>

            {cancellableTask ? (
              <button
                type="button"
                className="nb-ghost-btn"
                disabled={cancellingId === cancellableTask.id}
                onClick={() => handleCancelActiveTask(cancellableTask.id)}
              >
                {cancellingId === cancellableTask.id ? "取消中…" : "取消任务"}
              </button>
            ) : null}
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto">
            <VideoPanel
              tasks={sortedTasks}
              runningCount={wb.runningCount}
              activeTaskId={activeVideoTaskId}
              onDeleteTask={wb.removeVideoTask}
              onPlayTask={wb.playVideoTask}
            />
          </div>

          <div
            className="flex items-center justify-between"
            style={{
              marginTop: "var(--space-12)",
              paddingTop: "var(--space-8)",
              borderTop: "var(--border-width) solid var(--nb-border)",
              fontSize: 11,
              color: "var(--nb-text-tertiary)",
            }}
          >
            <span>
              侧栏 <kbd className="nb-kbd">⌘B</kbd>
            </span>
            <span>
              历史 <kbd className="nb-kbd">⌘H</kbd>
            </span>
          </div>
        </aside>
      </div>

      {/* 历史问答抽屉（右上角按钮或 Cmd/Ctrl+H 触发） */}
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
