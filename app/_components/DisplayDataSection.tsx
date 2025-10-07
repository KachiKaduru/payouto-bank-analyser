import { useParserStore } from "../_store/useParserStore";
import AnalysisSection from "./analysis/AnalysisSection";
import MetadataSection from "./metadata/MetadataSection";
import ResultsSection from "./results/ResultsSection";
import TableSection from "./table/TableSection";

export default function DisplayDataSection() {
  const activeTab = useParserStore((s) => s.activeTab);

  switch (activeTab) {
    case "analysis":
      return <AnalysisSection />;
    case "table":
      return <TableSection />;
    case "metadata":
      return <MetadataSection />;
    case "results":
      return <ResultsSection />;
    default:
      return null;
  }
}
