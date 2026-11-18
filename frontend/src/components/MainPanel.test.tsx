/**
 * 中栏问答主区单元测试（Step 3）：提问入口 + 引用条 + 答案区组合。
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MainPanel } from "./MainPanel";

describe("MainPanel 中栏问答主区", () => {
  it("无问题时渲染提问入口与空状态引导", () => {
    render(<MainPanel question="" answer="" citations={[]} progress={null} isAsking={false} refusalReason={null} confidence={null} error={null} onAsk={vi.fn()} examples={["示例"]} />);
    expect(screen.getByLabelText("提问")).toBeInTheDocument();
    expect(screen.getByText(/在上方输入问题并点击「提问」/)).toBeInTheDocument();
  });

  it("有问题时渲染引用条与答案正文", () => {
    render(
      <MainPanel
        question="q"
        answer="答"
        citations={[
          {
            doc_id: "doc05",
            doc_title: "t",
            source_file: "f.docx",
            heading_path: "h",
            para_id: "p1",
            snippet: "s",
            score: 0.9,
          },
        ]}
        progress={null}
        isAsking={false}
        refusalReason={null}
        confidence={null}
        error={null}
        onAsk={vi.fn()}
        examples={[]}
      />,
    );
    expect(screen.getByText("1 个来源")).toBeInTheDocument();
    expect(screen.getByText("f.docx")).toBeInTheDocument();
    expect(screen.getByText("答")).toBeInTheDocument();
  });

  it("max-width 720px 居中容器", () => {
    const { container } = render(<MainPanel question="" answer="" citations={[]} progress={null} isAsking={false} refusalReason={null} confidence={null} error={null} onAsk={vi.fn()} examples={[]} />);
    // MainPanel 根节点即 720px 容器
    const wrap = container.firstElementChild as HTMLElement;
    expect(wrap.style.maxWidth).toBe("720px");
  });
});
