import Stats from "./Stats";
import { useParserStore } from "../../_store/useParserStore";
import EmptyState from "../EmptyState";
import VirtualizedTable from "./VirtualizedTable";

export default function TableSection({ className = "" }: { className?: string }) {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);
  const viewFailedRows = useParserStore((s) => s.viewFailedRows);

  const failedData = data.filter((row) => row.Check === "FALSE");
  const displayedData = viewFailedRows ? failedData : data;

  if (loading && activeTab === "table") {
    return (
      <section className="border border-gray-300 rounded-xl w-full h-full p-6 animate-pulse">
        <h1 className="text-lg font-semibold mb-4">Table</h1>
        <p>Parsing bank statement…</p>
      </section>
    );
  }

  if (!data.length && activeTab === "table") return <EmptyState section="table" />;

  return (
    <div className={className}>
      <Stats />
      <VirtualizedTable rows={displayedData} />
    </div>
  );
}
