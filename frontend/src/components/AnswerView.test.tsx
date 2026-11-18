/**
 * 答案区单元测试（Step 3）：SSE 检索/生成阶段状态展示与流式正文、拒答与错误态。
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { AnswerView } from "./AnswerView";

describe("AnswerView 进度与答案展示", () => {
  it("检索阶段展示阶段名、消息与百分比", () => {
    render(
      <AnswerView
        question="q"
        answer=""
        progress={{ stage: "retrieval", message: "正在检索知识库…", progress: 0.1 }}
        isAsking
        refusalReason={null}
        confidence={null}
        error={null}
      />,
    );
    expect(screen.getByText(/检索阶段：正在检索知识库…（10%）/)).toBeInTheDocument();
  });

  it("生成阶段展示阶段名", () => {
    render(
      <AnswerView
        question="q"
        answer=""
        progress={{ stage: "generation", message: "正在生成回答…" }}
        isAsking
        refusalReason={null}
        confidence={null}
        error={null}
      />,
    );
    expect(screen.getByText(/生成阶段：正在生成回答…/)).toBeInTheDocument();
  });

  it("流式回答带光标，完成后无光标", () => {
    const { rerender } = render(
      <AnswerView question="q" answer="回答中" progress={null} isAsking refusalReason={null} confidence={null} error={null} />,
    );
    // 光标为独立 span 元素（与正文文本分离）
    expect(screen.getByText("回答中")).toBeInTheDocument();
    expect(document.querySelector("span")?.textContent).toBe("▍");
    rerender(
      <AnswerView question="q" answer="回答中" progress={null} isAsking={false} refusalReason={null} confidence={0.9} error={null} />,
    );
    expect([...document.querySelectorAll("span")].every((s) => s.textContent !== "▍")).toBe(true);
    expect(screen.getByText("可信度 90%")).toBeInTheDocument();
  });

  it("拒答展示原因且不展示可信度", () => {
    render(
      <AnswerView
        question="q"
        answer="文档未给出确定数值，无法回答该问题。"
        progress={null}
        isAsking={false}
        refusalReason="E_OUT_OF_KNOWLEDGE"
        confidence={null}
        error={null}
      />,
    );
    expect(screen.getByText("文档未给出确定数值，无法回答该问题。")).toBeInTheDocument();
    expect(screen.getByText(/拒答原因：E_OUT_OF_KNOWLEDGE/)).toBeInTheDocument();
    expect(screen.queryByText(/可信度/)).not.toBeInTheDocument();
  });

  it("错误态以完整句子展示", () => {
    render(
      <AnswerView question="q" answer="" progress={null} isAsking={false} refusalReason={null} confidence={null} error="E_LLM_FAILED：模型调用失败" />,
    );
    expect(screen.getByText("E_LLM_FAILED：模型调用失败")).toBeInTheDocument();
  });

  it("空状态给出完整句子引导", () => {
    render(
      <AnswerView question="" answer="" progress={null} isAsking={false} refusalReason={null} confidence={null} error={null} />,
    );
    expect(screen.getByText(/在上方输入问题并点击「提问」/)).toBeInTheDocument();
  });

  it("generation 阶段无 progress 字段时不展示百分比", () => {
    render(
      <AnswerView
        question="q"
        answer=""
        progress={{ stage: "generation", message: "正在生成回答…" }}
        isAsking
        refusalReason={null}
        confidence={null}
        error={null}
      />,
    );
    expect(screen.getByText("生成阶段：正在生成回答…")).toBeInTheDocument();
  });
});
