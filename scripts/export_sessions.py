"""导出 Claude Code 会话 transcript 为可读 Markdown（写入 sessions/）。

读取 ~/.claude/projects/<本项目目录>/*.jsonl，提取用户提问与助手正文，
按会话写入 sessions/<名称>.md，保留现有文件头（标题/Session ID/时间）。
仅读不写 transcript 原文。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROJECT_DIR = Path.home() / ".claude" / "projects" / "C--Users-18712-Downloads--------4-"
SESSIONS = Path(__file__).resolve().parents[1] / "sessions"

# sessions/<文件名> <- transcript <sessionId>
NAME_BY_ID = {
    "b62c1ebb-7a45-42c2-80ac-ec675523f6de": "初始化.md",
    "f0e73542-1191-41e6-9222-12f6cf200f98": "前端.md",
    "318a64ae-2f60-4571-8044-7a136acd4664": "后端.md",
    "6afc159c-335d-4593-a6f8-c59541e72301": "eval与验收.md",
    "63e10b78-8a7d-4129-8e29-45e55a356e97": "bugfix.md",
}


def text_of(content) -> str:
    """从 message.content（str 或 block 列表）提取纯文本。"""
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        t = b.get("type")
        if t == "text":
            parts.append(b.get("text", ""))
        elif t == "tool_use":
            name = b.get("name", "?")
            inp = json.dumps(b.get("input", {}), ensure_ascii=False)
            parts.append(f"【调用工具 {name}】```json\n{inp}\n```")
        elif t == "tool_result":
            c = b.get("content", "")
            c = text_of(c) if not isinstance(c, str) else c
            parts.append(f"【工具返回】\n```\n{c[:2000]}\n```")
    return "\n".join(p for p in parts if p)


def extract(md_path: Path) -> list[dict]:
    """从 jsonl 提取 user/assistant 消息（跳过 attachment/queue-operation）。"""
    out: list[dict] = []
    for line in md_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = rec.get("type")
        if kind not in ("user", "assistant"):
            continue
        msg = rec.get("message") or {}
        role = msg.get("role", kind)
        body = text_of(msg.get("content"))
        if not body.strip():
            continue
        # 剥离工具返回占位与纯系统提示噪声
        if role == "user" and body.startswith("<"):
            continue
        out.append({"role": role, "text": body.strip(), "ts": rec.get("timestamp", "")})
    return out


def render(sid: str, msgs: list[dict], header: str) -> str:
    lines = [header, "", "---", ""]
    for m in msgs:
        tag = "用户" if m["role"] == "user" else "Claude"
        lines.append(f"## [{tag}] {m['ts']}")
        lines.append("")
        lines.append(m["text"].strip())
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    made = []
    for sid, name in NAME_BY_ID.items():
        src = PROJECT_DIR / f"{sid}.jsonl"
        if not src.exists():
            print(f"[skip] {name}: transcript 不存在 {src.name}")
            continue
        msgs = extract(src)
        if not msgs:
            print(f"[skip] {name}: 无可提取消息")
            continue
        # 复用现有文件头（标题 + 元信息），替换正文
        dst = SESSIONS / name
        header = dst.read_text(encoding="utf-8").split("---")[0].strip() if dst.exists() else f"# {name}"
        dst.write_text(render(sid, msgs, header), encoding="utf-8")
        made.append((name, len(msgs), dst.stat().st_size))
        print(f"[ok] {name}: {len(msgs)} 条消息, {dst.stat().st_size} bytes")
    print("导出完成:", made)


if __name__ == "__main__":
    main()
