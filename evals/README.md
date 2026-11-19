# evals/

Eval 验收 Agent 专用区域。按 `CLAUDE.md` §四 盲测隔离：前端/后端开发 Agent
严禁读取 `docs/EVAL.md`；本目录存放评估运行器与验收报告。

## 运行器

```bash
# 前置：后端已启动（bash start.sh 或 uvicorn），知识库 7 篇文档已入库
python evals/run_eval.py --reset
```

- 黑盒驱动真实链路（入库 → 本地混合检索 → LLM 问答 → SSE → 单并发视频队列），
  **严禁 Mock**：答案必须来自真实 LLM 调用，视频必须真实合成落盘；
- 依次执行 `docs/EVAL.md` 的 14 条黄金用例（A 单文档事实 / B 易混对比 /
  C 跨文档时间线 / D 抗注入 / E 边界拒答 / F 队列压测）；
- E13/E14 运行前自动等待队列排空（FIFO 位置断言的前提），评估全程含真实视频合成，
  单轮耗时约 10–20 分钟；
- 产出 `evals/eval_report.md`：逐题通过情况、引用召回率、抗注入/拒答正确率、
  并发校验明细与失败要点。报告只回传 pass/fail 与失败类别，不回写期望答案。

## 报告

- `evals/eval_report.md`（`--reset` 自动覆盖；已被 `.gitignore` 忽略，只提交模板与说明）
- 历史副本可存 `evals/reports/`（同样 gitignore）

## 数据集

- `docs/EVAL.md`（14 条用例，Eval Agent 专读）
