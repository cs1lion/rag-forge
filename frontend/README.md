# frontend

React + TypeScript + Tailwind。会话 1 基线仅含脚手架骨架与令牌生效验证；
编辑型工作台三栏布局（文档库 / 问答与引用 / 任务队列与历史）在后续会话实现。

视觉唯一来源：`DESIGN.md` 与 `design/tokens.css`（禁止在组件里硬编码色值）。

## 运行

```bash
npm install
cp .env.example .env   # 如需改端口
npm run dev            # http://localhost:5173
```

## 注意

前端开发 Agent 严禁读取 `docs/EVAL.md`（盲测隔离，见 `CLAUDE.md` §四）。
