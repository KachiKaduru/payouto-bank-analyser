import { useParserStore } from "../_store/useParserStore";
import EmptyState from "./EmptyState";

export default function Analysis() {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

  // console.log(data);

  if (loading) {
    return (
      <section className="border border-gray-300 rounded-xl w-full h-full p-6 animate-pulse">
        <h1 className="text-lg font-semibold mb-4">Analysis</h1>
        <p>Crunching numbers…</p>
      </section>
    );
  }

  if (!data?.length && activeTab === "analysis") {
    return <EmptyState section="analysis" />;
  }

  return (
    <section className="border border-gray-300 p-6 rounded-2xl">
      <h1>Analysis part</h1>
    </section>
  );
}
