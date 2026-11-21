import { useCallback, useState } from "react";

export interface DocumentItem {
  doc_id: string;
  title: string;
  source_file: string;
  char_count: number;
  injection_flag: number;
  risk_warning?: string | null;
}

/**
 * P3 领域拆分 Hook（文档域）：管理知识库文档列表、勾选检索范围与风险筛选，
 * 与高频 SSE 问答流 / 视频队列状态隔离，避免无关面板重渲染。
 */
export function useDocuments(initialDocs: DocumentItem[] = []) {
  const [documents, setDocuments] = useState<DocumentItem[]>(initialDocs);
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>(() =>
    initialDocs.map((d) => d.doc_id)
  );
  const [loading, setLoading] = useState(false);

  const refreshDocuments = useCallback(async (fetcher: () => Promise<DocumentItem[]>) => {
    setLoading(true);
    try {
      const list = await fetcher();
      setDocuments(list);
      setSelectedDocIds((prev) =>
        prev.length === 0 ? list.map((d) => d.doc_id) : prev.filter((id) => list.some((d) => d.doc_id === id))
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const toggleDoc = useCallback((docId: string) => {
    setSelectedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    );
  }, []);

  const selectAll = useCallback(() => {
    setSelectedDocIds(documents.map((d) => d.doc_id));
  }, [documents]);

  const clearSelection = useCallback(() => {
    setSelectedDocIds([]);
  }, []);

  return {
    documents,
    selectedDocIds,
    loading,
    setDocuments,
    refreshDocuments,
    toggleDoc,
    selectAll,
    clearSelection,
  };
}
