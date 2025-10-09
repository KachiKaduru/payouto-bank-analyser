import { useParserStore } from "../_store/useParserStore";
import AnalysisSection from "./analysis/AnalysisSection";
import MetadataSection from "./metadata/MetadataSection";
import ResultsSection from "./results/ResultsSection";
import TableSection from "./table/TableSection";

export default function DisplayDataSection() {
  const activeTab = useParserStore((s) => s.activeTab);

  return (
    <div>
      {/* <div className="h-full max-h-[86dvhh] overflow-auto rounded-2xl bg-white/50  border border-gray-200 p-4"> */}
      {activeTab === "analysis" && <AnalysisSection />}
      {activeTab === "table" && <TableSection />}
      {activeTab === "metadata" && <MetadataSection />}
      {activeTab === "results" && <ResultsSection />}
    </div>
  );
}
