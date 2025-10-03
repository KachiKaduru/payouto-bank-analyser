import Stats from "./Stats";
import ResultsTable from "./ResultsTable";
import { useParserStore } from "../_store/useParserStore";
import EmptyState from "./EmptyState";

export default function TableData({ className = "" }: { className?: string }) {
  const data = useParserStore((s) => s.data);
  const activeTab = useParserStore((s) => s.activeTab);

  if (!data.length && activeTab === "table") return <EmptyState section="table" />;

  return (
    <div className={className}>
      <Stats />
      <ResultsTable />
    </div>
  );
}
