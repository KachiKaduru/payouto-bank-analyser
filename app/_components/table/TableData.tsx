import Stats from "./Stats";
import ResultsTable from "./ResultsTable";
import { useParserStore } from "../../_store/useParserStore";
import EmptyState from "../EmptyState";

export default function TableData({ className = "" }: { className?: string }) {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

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
      <ResultsTable />
    </div>
  );
}
