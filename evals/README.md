# evals/

Eval 验收 Agent 专用区域。按 `CLAUDE.md` §四 盲测隔离：前端/后端开发 Agent
严禁读取 `docs/EVAL.md`；本目录存放评估运行器与验收报告。

- 运行器：后续会话实现（如 `evals/run_eval.py`）
- 报告：`evals/reports/`（已被 `.gitignore` 忽略，只提交模板与说明）
- 数据集：`docs/EVAL.md`（14 条用例，Eval Agent 专用）
