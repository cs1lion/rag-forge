/**
 * 顶栏（DESIGN.md §6）：高 56px、底部 1px 描边；左侧标题 + 星标线性图标，
 * 右侧圆形图标按钮组；主操作仅一个实心胶囊按钮「+ 创建」。
 */
import { Icon } from "./Icon";

interface TopBarProps {
  onCreate: () => void;
  onToggleSidebar: () => void;
  sidebarOpen: boolean;
  onOpenHistory: () => void;
}

export function TopBar({ onCreate, onToggleSidebar, sidebarOpen, onOpenHistory }: TopBarProps) {
  return (
    <header
      className="flex items-center justify-between"
      style={{
        height: "56px",
        padding: "0 var(--space-16)",
        borderBottom: "var(--border-width) solid var(--nb-border)",
        backgroundColor: "var(--nb-bg)",
      }}
    >
      <div className="flex items-center" style={{ gap: "var(--space-8)" }}>
        <button
          type="button"
          aria-label={sidebarOpen ? "收起侧栏" : "展开侧栏"}
          onClick={onToggleSidebar}
          className="flex items-center justify-center rounded-full transition-colors"
          style={{ width: 32, height: 32 }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
        >
          <Icon name="layers" size={20} style={{ color: "var(--nb-text-secondary)" }} />
        </button>
        <h1
          style={{
            fontSize: "var(--text-card-title-size-zh)",
            lineHeight: "var(--text-card-title-line-height)",
            fontWeight: "var(--text-card-title-weight)",
            color: "var(--nb-text)",
          }}
        >
          伏光 · 知识库问答工作台
        </h1>
        <Icon name="star" size={16} style={{ color: "var(--nb-text-tertiary)" }} />
      </div>

      <div className="flex items-center" style={{ gap: "var(--space-8)" }}>
        <button
          type="button"
          aria-label="历史问答"
          onClick={onOpenHistory}
          className="flex items-center justify-center rounded-full transition-colors"
          style={{ width: 32, height: 32 }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
        >
          <Icon name="history" size={20} style={{ color: "var(--nb-text-secondary)" }} />
        </button>
        <button
          type="button"
          onClick={onCreate}
          className="flex items-center rounded-pill transition-colors"
          style={{
            height: 36,
            padding: "0 var(--space-20)",
            backgroundColor: "var(--nb-accent)",
            color: "#FFFFFF",
            fontSize: "var(--text-body-size)",
            fontWeight: 500,
            gap: "var(--space-8)",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-accent-hover)")}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-accent)")}
        >
          <Icon name="plus" size={16} />
          创建
        </button>
      </div>
    </header>
  );
}
