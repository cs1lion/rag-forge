/**
 * 左侧栏（Step 2）：文档库（上传承 + 列表 + 删除）与历史问答（点击回看）。
 * 侧栏底色 --nb-bg-subtle，与中栏以 1px 描边分隔。
 */
import { Panel } from "./Panel";
import { DocUploader } from "./DocUploader";
import { DocList } from "./DocList";
import { HistoryList } from "./HistoryList";
import type { DocumentRecord, QaRecordSummary } from "../types";

interface SidebarProps {
  documents: DocumentRecord[];
  qaRecords: QaRecordSummary[];
  selectedHistoryId: number | null;
  onUpload: (file: File) => Promise<void>;
  onDeleteDoc: (docId: string) => Promise<void>;
  onSelectHistory: (id: number) => Promise<void>;
  uploading: boolean;
}

export function Sidebar(props: SidebarProps) {
  return (
    <div className="flex min-h-0 flex-col" style={{ height: "100%", gap: "var(--space-16)" }}>
      <Panel title="文档库" meta={`${props.documents.length} 篇`} className="flex min-h-0 flex-1 flex-col">
        <DocUploader onUpload={props.onUpload} disabled={props.uploading} />
        <div className="min-h-0 flex-1 overflow-y-auto">
          <DocList documents={props.documents} onDelete={props.onDeleteDoc} busy={props.uploading} />
        </div>
      </Panel>

      <Panel title="历史问答" meta={`${props.qaRecords.length} 条`} className="flex min-h-0 flex-1 flex-col">
        <div className="min-h-0 flex-1 overflow-y-auto">
          <HistoryList records={props.qaRecords} selectedId={props.selectedHistoryId} onSelect={props.onSelectHistory} />
        </div>
      </Panel>
    </div>
  );
}
