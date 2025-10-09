import Stats from "./Stats";
import { useParserStore } from "../../_store/useParserStore";
import EmptyState from "../_ui/EmptyState";
import VirtualizedTable from "./VirtualizedTable";
import LoadingState from "../_ui/LoadingState";

export default function TableSection({ className = "" }: { className?: string }) {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);
  const viewFailedRows = useParserStore((s) => s.viewFailedRows);

  const failedData = data.filter((row) => row.Check === "FALSE");
  const displayedData = viewFailedRows ? failedData : data;

  if (loading && activeTab === "table") {
    return <LoadingState currentTab={activeTab} text="Parsing bank statement…" />;
  }

  if (!data.length && activeTab === "table") return <EmptyState section="table" />;

  return (
    <div className={`${className} space-y-6`}>
      <Stats />
      <VirtualizedTable rows={displayedData} />
    </div>
  );
}
