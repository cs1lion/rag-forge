/**
 * App 集成测试：三栏骨架 + 顶栏 + 错误横幅 + 提问联动。
 */
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

const QA_SUMMARY = {
  id: 1,
  question: "众赢科技 2025 年研发投入占营收比重是多少？",
  answer_summary: "超过 75%。",
  video_task_id: 3,
  video_status: "done" as const,
  created_at: "2026-11-18T10:00:00Z",
};

describe("App 三栏工作台", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [QA_SUMMARY], total: 1 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        if (url === "/api/qa/ask")
          return new Response(
            'event: qa.progress\ndata: {"stage":"retrieval","message":"正在检索知识库…","progress":0.1}\n\n' +
              'event: qa.citations\ndata: {"citations":[]}\n\n' +
              'event: qa.answer\ndata: {"delta":"回答正文。"}\n\n' +
              'event: qa.done\ndata: {"qa_record_id":2,"video_task_id":4}\n\n',
            { headers: { "Content-Type": "text/event-stream" } },
          );
        return new Response(null, { status: 404 });
      }),
    );
  });

  afterEach(() => vi.unstubAllGlobals());

  it("三栏标题与顶栏「+ 创建」均渲染", async () => {
    render(<App />);
    expect(screen.getByText("伏光 · 知识库问答工作台")).toBeInTheDocument();
    expect(screen.getByText("文档库")).toBeInTheDocument();
    expect(screen.getByText("视频工作室")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /创建/ })).toBeInTheDocument();
    // 历史问答已迁至顶栏抽屉：默认不渲染历史列表
    expect(screen.queryByText("共 1 条记录")).not.toBeInTheDocument();
    // 顶栏历史按钮可点击打开抽屉
    await userEvent.click(screen.getByLabelText("历史问答"));
    await waitFor(() => expect(screen.getByText("共 1 条记录")).toBeInTheDocument());
    // 抽屉内渲染历史问题文本（与示例问题重名，限定在 dialog 内查询）
    const dialog = screen.getByRole("dialog");
    await waitFor(() => expect(dialog.textContent).toContain(QA_SUMMARY.question));
  });

  it("输入问题并提交后展示问题与流式回答", async () => {
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("提问")).toBeInTheDocument());
    await user.type(screen.getByLabelText("提问"), "研发投入占比？");
    await user.click(screen.getByRole("button", { name: "提问" }));
    await waitFor(() => expect(screen.getByText("研发投入占比？")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("回答正文。")).toBeInTheDocument());
  });

  it("后端错误时顶栏下展示可关闭的错误横幅", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/documents") throw new Error("网络断开");
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    render(<App />);
    const banner = await screen.findByText(/文档列表加载失败/);
    expect(banner).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("关闭错误提示"));
    await waitFor(() => expect(screen.queryByText(/文档列表加载失败/)).not.toBeInTheDocument());
  });

  it("侧栏折叠按钮切换左栏宽度", async () => {
    render(<App />);
    const toggle = screen.getByLabelText("收起侧栏");
    toggle.click();
    await waitFor(() => expect(screen.getByLabelText("展开侧栏")).toBeInTheDocument());
  });

  it("顶栏「+ 创建」发起示例问题问答", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByRole("button", { name: /创建/ })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /创建/ }));
    await waitFor(() => expect(screen.getByText("回答正文。")).toBeInTheDocument());
  });

  it("视频任务按 running > queued > 其余排序展示", async () => {
    const mk = (id: number, status: "running" | "queued" | "done" | "failed") => ({
      id,
      qa_record_id: id,
      status,
      progress: status === "done" ? 1 : 0.3,
      queue_position: status === "queued" ? id : undefined,
      video_url: status === "done" ? `/api/videos/${id}/file` : null,
      error: null,
      created_at: "2026-11-18T10:00:00Z",
      started_at: null,
      finished_at: null,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/documents") return Response.json({ documents: [], total: 0 });
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks")
          return Response.json({ tasks: [mk(9, "done"), mk(5, "queued"), mk(2, "running")], running_count: 1 });
        return new Response(null, { status: 404 });
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText("视频任务 #2")).toBeInTheDocument());
    const titles = screen.getAllByText(/视频任务 #/).map((el) => el.textContent);
    expect(titles[0]).toContain("#2");
    expect(titles[1]).toContain("#5");
    expect(titles[2]).toContain("#9");
  });

  it("上传文档后刷新文档列表并显示新文档", async () => {
    const user = userEvent.setup();
    let uploaded = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === "/api/documents" && init?.method === "POST") {
          uploaded = true;
          return Response.json({
            document: { doc_id: "doc09", title: "新入库文档", source_file: "new.md", source_format: "md", parse_method: "MD 直读", char_count: 10, injection_flag: 0, chunk_count: 1, created_at: "2026-11-18T10:00:00Z" },
          });
        }
        if (url === "/api/documents")
          return Response.json(
            uploaded
              ? { documents: [{ doc_id: "doc09", title: "新入库文档", source_file: "new.md", source_format: "md", parse_method: "MD 直读", char_count: 10, injection_flag: 0, chunk_count: 1, created_at: "2026-11-18T10:00:00Z" }], total: 1 }
              : { documents: [], total: 0 },
          );
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByText("文档库")).toBeInTheDocument());
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["# 新"], "new.md", { type: "text/markdown" }));
    await waitFor(() => expect(screen.getByText("新入库文档")).toBeInTheDocument());
    expect(screen.getByLabelText("选择文档 新入库文档")).toBeChecked();
  });

  it("取消所有文档后发送按钮禁用并展示提示", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/documents")
          return Response.json({ documents: [{ doc_id: "doc01", title: "唯一文档", source_file: "one.md", source_format: "md", parse_method: "MD 直读", char_count: 10, injection_flag: 0, risk_warning: null, chunk_count: 1, created_at: "2026-11-18T10:00:00Z" }], total: 1 });
        if (url === "/api/qa") return Response.json({ records: [], total: 0 });
        if (url === "/api/video-tasks") return Response.json({ tasks: [], running_count: 0 });
        return new Response(null, { status: 404 });
      }),
    );
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("选择文档 唯一文档")).toBeChecked());
    await userEvent.click(screen.getByLabelText("全选文档"));
    expect(screen.getByLabelText("选择文档 唯一文档")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "提问" })).toBeDisabled();
    expect(screen.getByText("请至少勾选 1 份知识库文档")).toBeInTheDocument();
  });
});
