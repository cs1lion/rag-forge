/**
 * 已入库文档列表（Step 2）：行高 36–40px、单行截断、悬停整行填充，
 * 右侧 12px 说明文字 + 删除图标按钮；含注入隔离标记。
 */
import { Icon } from "./Icon";
import type { DocumentRecord } from "../types";

interface DocListProps {
  documents: DocumentRecord[];
  onDelete: (docId: string) => Promise<void>;
  busy?: boolean;
}

export function DocList({ documents, onDelete, busy }: DocListProps) {
  return (
    <ul role="list" aria-label="已入库文档" style={{ padding: "0 var(--space-8) var(--space-8)" }}>
      {documents.length === 0 ? (
        <li
          style={{
            padding: "var(--space-12) var(--space-8)",
            fontSize: "var(--text-body-size)",
            color: "var(--nb-text-tertiary)",
          }}
        >
          知识库暂无文档，上传 .md / .docx / .doc 文件后即可提问。
        </li>
      ) : (
        documents.map((doc) => (
          <li
            key={doc.doc_id}
            className="group flex items-center transition-colors"
            style={{
              height: 40,
              padding: "0 var(--space-8)",
              gap: "var(--space-8)",
              borderRadius: "var(--nb-radius-sm)",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg-hover)")}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
          >
            <Icon name="file" size={16} style={{ color: "var(--nb-text-tertiary)", flexShrink: 0 }} />
            <span
              className="min-w-0 flex-1"
              style={{
                fontSize: "var(--text-body-size)",
                color: "var(--nb-text-secondary)",
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
              title={doc.title}
            >
              {doc.title}
            </span>
            {doc.injection_flag === 1 ? (
              <span
                className="rounded-sm"
                style={{
                  fontSize: "var(--text-micro-label-size)",
                  lineHeight: "var(--text-micro-label-line-height)",
                  fontWeight: "var(--text-micro-label-weight)",
                  letterSpacing: "var(--text-micro-label-letter-spacing)",
                  padding: "2px 6px",
                  backgroundColor: "var(--nb-tint-amber-bg)",
                  color: "var(--nb-tint-amber-ink)",
                }}
                title="该文档含疑似越权指令文本，已隔离，不参与检索"
              >
                已隔离
              </span>
            ) : null}
            <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)", flexShrink: 0 }}>
              {doc.char_count} 字
            </span>
            <button
              type="button"
              aria-label={`删除文档 ${doc.title}`}
              disabled={busy}
              onClick={() => void onDelete(doc.doc_id)}
              className="flex items-center justify-center rounded-full opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100"
              style={{ width: 28, height: 28, flexShrink: 0 }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "var(--nb-bg)")}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
            >
              <Icon name="trash" size={16} style={{ color: "var(--nb-text-tertiary)" }} />
            </button>
          </li>
        ))
      )}
    </ul>
  );
}
