/**
 * 顶栏单元测试（DESIGN.md §6）：56px 高、底部 1px 描边、唯一实心胶囊「+ 创建」。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TopBar } from "./TopBar";

describe("TopBar 顶栏", () => {
  it("高度 56px、底部 1px 描边、标题与星标图标在列", () => {
    render(<TopBar onCreate={vi.fn()} onToggleSidebar={vi.fn()} sidebarOpen onOpenHistory={vi.fn()} />);
    const header = screen.getByRole("banner");
    expect(header.style.height).toBe("56px");
    expect(header.style.borderBottom).toContain("var(--nb-border)");
    expect(screen.getByText("伏光 · 知识库问答工作台")).toBeInTheDocument();
    expect(screen.getByLabelText("收起侧栏")).toBeInTheDocument();
  });

  it("侧栏收起时按钮 aria-label 切换为「展开侧栏」", () => {
    render(<TopBar onCreate={vi.fn()} onToggleSidebar={vi.fn()} sidebarOpen={false} onOpenHistory={vi.fn()} />);
    expect(screen.getByLabelText("展开侧栏")).toBeInTheDocument();
  });

  it("「+ 创建」为唯一实心主按钮并触发 onCreate", () => {
    const onCreate = vi.fn();
    render(<TopBar onCreate={onCreate} onToggleSidebar={vi.fn()} sidebarOpen onOpenHistory={vi.fn()} />);
    const btn = screen.getByRole("button", { name: /创建/ });
    expect(btn.style.backgroundColor).toBe("var(--nb-accent)");
    fireEvent.click(btn);
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("侧栏切换按钮触发 onToggleSidebar", () => {
    const onToggle = vi.fn();
    render(<TopBar onCreate={vi.fn()} onToggleSidebar={onToggle} sidebarOpen onOpenHistory={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("收起侧栏"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("历史按钮触发 onOpenHistory", () => {
    const onOpenHistory = vi.fn();
    render(<TopBar onCreate={vi.fn()} onToggleSidebar={vi.fn()} sidebarOpen onOpenHistory={onOpenHistory} />);
    fireEvent.click(screen.getByLabelText("历史问答"));
    expect(onOpenHistory).toHaveBeenCalledTimes(1);
  });

  it("图标按钮与创建按钮悬停填充令牌色", () => {
    render(<TopBar onCreate={vi.fn()} onToggleSidebar={vi.fn()} sidebarOpen onOpenHistory={vi.fn()} />);
    for (const label of ["收起侧栏", "历史问答"]) {
      const btn = screen.getByLabelText(label);
      fireEvent.mouseEnter(btn);
      expect(btn.style.backgroundColor).toBe("var(--nb-bg-hover)");
      fireEvent.mouseLeave(btn);
      expect(btn.style.backgroundColor).toBe("transparent");
    }
    const create = screen.getByRole("button", { name: /创建/ });
    fireEvent.mouseEnter(create);
    expect(create.style.backgroundColor).toBe("var(--nb-accent-hover)");
    fireEvent.mouseLeave(create);
    expect(create.style.backgroundColor).toBe("var(--nb-accent)");
  });
});
