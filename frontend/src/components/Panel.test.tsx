/**
 * 面板容器单元测试（DESIGN.md §5/§6）：白底 + 1px 描边 + 12px 圆角、无阴影。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Panel } from "./Panel";

describe("Panel 面板容器", () => {
  it("渲染标题、元信息与子内容", () => {
    render(
      <Panel title="文档库" meta="3 篇">
        <p>子内容</p>
      </Panel>,
    );
    expect(screen.getByText("文档库")).toBeInTheDocument();
    expect(screen.getByText("3 篇")).toBeInTheDocument();
    expect(screen.getByText("子内容")).toBeInTheDocument();
  });

  it("无 meta 时不渲染元信息行", () => {
    render(<Panel title="问答">x</Panel>);
    expect(screen.getByText("问答")).toBeInTheDocument();
  });

  it("样式为白底 + 1px 描边 + 12px 圆角、无阴影", () => {
    render(<Panel title="t">x</Panel>);
    const section = screen.getByText("t").closest("section")!;
    expect(section.style.backgroundColor).toBe("var(--nb-bg)");
    expect(section.style.border).toContain("var(--nb-border)");
    // 圆角经 Tailwind rounded-md（映射 --nb-radius-md）而非内联样式
    expect(section.className).toContain("rounded-md");
    expect(section.style.boxShadow).toBe("");
  });
});
