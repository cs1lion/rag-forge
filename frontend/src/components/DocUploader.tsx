/**
 * 文档拖拽上传区（Step 2）：支持 .md / .docx / .doc；
 * 拖拽悬停整行填充 --nb-bg-hover；仅接受三类扩展名，其余给出完整句子提示。
 */
import { useRef, useState } from "react";
import { Icon } from "./Icon";

const ACCEPTED = [".md", ".docx", ".doc"];

interface DocUploaderProps {
  onUpload: (file: File) => Promise<void>;
  disabled?: boolean;
}

export function DocUploader({ onUpload, disabled }: DocUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [rejectMsg, setRejectMsg] = useState<string | null>(null);

  const acceptFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const file = files[0];
    const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
    if (!ACCEPTED.includes(ext)) {
      // 拒绝信息需与占位文案区分，避免文本匹配歧义
      setRejectMsg(`文件 ${file.name} 无法入库：仅支持 .md / .docx / .doc 文档。`);
      return;
    }
    setRejectMsg(null);
    void onUpload(file);
  };

  return (
    <div style={{ padding: "0 var(--space-16) var(--space-8)" }}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          acceptFiles(e.dataTransfer.files);
        }}
        className="flex w-full flex-col items-center justify-center transition-colors"
        style={{
          minHeight: 96,
          gap: "var(--space-8)",
          border: "1px dashed var(--nb-border-strong)",
          borderRadius: "var(--nb-radius-sm)",
          backgroundColor: dragOver ? "var(--nb-bg-hover)" : "var(--nb-bg-subtle)",
          cursor: disabled ? "not-allowed" : "pointer",
          opacity: disabled ? 0.5 : 1,
        }}
      >
        <Icon name="upload" size={20} style={{ color: "var(--nb-text-tertiary)" }} />
        <span style={{ fontSize: "var(--text-body-size)", color: "var(--nb-text-secondary)" }}>
          拖拽文档到此处，或点击选择文件
        </span>
        <span style={{ fontSize: "var(--text-meta-size)", color: "var(--nb-text-tertiary)" }}>
          支持 .md / .docx / .doc
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        // accept 属性会让测试工具与浏览器在选文件阶段就过滤扩展名，
        // 拒绝逻辑统一在 JS 层完成并给出完整句子提示（DESIGN.md §8）
        className="hidden"
        onChange={(e) => {
          acceptFiles(e.target.files);
          e.target.value = "";
        }}
      />
      {rejectMsg ? (
        <p role="alert" style={{ marginTop: "var(--space-8)", fontSize: "var(--text-meta-size)", color: "var(--nb-tint-amber-ink)" }}>
          {rejectMsg}
        </p>
      ) : null}
    </div>
  );
}
