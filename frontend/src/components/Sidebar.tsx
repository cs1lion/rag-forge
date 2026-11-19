/**
 * 左侧栏（Step 2）：文档库（上传承 + 列表 + 隔离开关 + 删除）。
 * 侧栏底色 --nb-bg-subtle，与中栏以 1px 描边分隔。
 * 历史问答列表已迁至顶栏「历史」按钮弹层（会话 4），侧栏不再承载。
 */
import { Panel } from "./Panel";
import { DocUploader } from "./DocUploader";
import { DocList } from "./DocList";
import type { DocumentRecord } from "../types";

interface SidebarProps {
  documents: DocumentRecord[];
  selectedDocIds: string[];
  onToggleDoc: (docId: string) => void;
  onToggleAllDocs: () => void;
  onUpload: (file: File) => Promise<void>;
  onDeleteDoc: (docId: string) => Promise<void>;
  uploading: boolean;
}

export function Sidebar(props: SidebarProps) {
  return (
    <div className="flex min-h-0 flex-col" style={{ height: "100%", gap: "var(--space-16)" }}>
      <Panel title="文档库" meta={`${props.documents.length} 篇`} className="flex min-h-0 flex-1 flex-col">
        <DocUploader onUpload={props.onUpload} disabled={props.uploading} />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <DocList
            documents={props.documents}
            selectedIds={props.selectedDocIds}
            onToggleDoc={props.onToggleDoc}
            onToggleAll={props.onToggleAllDocs}
            onDelete={props.onDeleteDoc}
            busy={props.uploading}
          />
        </div>
      </Panel>
    </div>
  );
}
