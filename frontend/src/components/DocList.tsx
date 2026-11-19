/**
 * 已入库文档列表（Step 2）：勾选生效范围 + 全选 + 删除。
 * 行高 36–40px、单行截断、悬停整行填充；含入库自动识别的风险徽标。
 *
 * 勾选语义：勾选的文档构成本次问答的检索范围（默认全选）；
 * 取消全部勾选时提问会被阻止并给出完整句子提示。
 * 风险提示：入库时自动识别疑似越权指令文本并过滤相关段落（不再提供手动隔离开关），
 * 含风险文档以「含风险」徽标与 tooltip 明示，引用该文件时在来源条再次提示。
 */
import { Icon } from "./Icon";
import type { DocumentRecord } from "../types";

interface DocListProps {
  documents: DocumentRecord[];
  selectedIds: string[];
  onToggleDoc: (docId: string) => void;
  onToggleAll: () => void;
  onDelete: (docId: string) => Promise<void>;
  busy?: boolean;
}

export function DocList({ documents, selectedIds, onToggleDoc, onToggleAll, onDelete, busy }: DocListProps) {
  const allSelected = documents.length > 0 && selectedIds.length === documents.length;

  return (
    <div>
      <div
        className="flex items-center"
        style={{ padding: "0 var(--space-16) var(--space-8)", gap: "var(--space-8)" }}
      >
        <input
          type="checkbox"
          aria-label="全选文档"
          checked={allSelected}
          disabled={documents.length === 0}
          onChange={onToggleAll}
          style={{ width: 15, height: 15, accentColor: "var(--nb-accent)", cursor: "pointer" }}
        />
        <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
          全选 · 已选 {selectedIds.length} / {documents.length} 篇生效
        </span>
      </div>

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
          documents.map((doc) => {
            const checked = selectedIds.includes(doc.doc_id);
            return (
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
                <input
                  type="checkbox"
                  aria-label={`选择文档 ${doc.title}`}
                  checked={checked}
                  onChange={() => onToggleDoc(doc.doc_id)}
                  style={{ width: 15, height: 15, accentColor: "var(--nb-accent)", cursor: "pointer", flexShrink: 0 }}
                />
                <Icon name="file" size={16} style={{ color: "var(--nb-text-tertiary)", flexShrink: 0 }} />
                <span
                  className="min-w-0 flex-1"
                  style={{
                    fontSize: "var(--text-body-size)",
                    color: checked ? "var(--nb-text-secondary)" : "var(--nb-text-tertiary)",
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
                      flexShrink: 0,
                    }}
                    title="入库时自动识别到疑似越权指令文本，相关段落已自动过滤、不参与检索；引用本文件时会在来源条提示风险"
                  >
                    含风险
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
            );
          })
        )}
      </ul>
    </div>
  );
}
