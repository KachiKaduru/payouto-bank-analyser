import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatNaira } from "@/app/_utils/helpers";

export default function SummaryTiles() {
  const totals = useAnalysisStore((s) => s.totals);

  if (totals.credit === 0 && totals.debit === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 tracking-wide">
      <div className="rounded-2xl border border-gray-400 p-4">
        <div className="text-sm text-gray-500">Total Credit</div>
        <div className="text-xl font-semibold">{formatNaira(totals.credit)}</div>
      </div>
      <div className="rounded-2xl border border-gray-400 p-4 ">
        <div className="text-sm text-gray-500">Total Debit</div>
        <div className="text-xl font-semibold">{formatNaira(totals.debit)}</div>
      </div>
      <div className="rounded-2xl border border-gray-400 p-4 ">
        <div className="text-sm text-gray-500">Net</div>
        <div
          className={`text-xl font-semibold ${
            totals.net >= 0 ? "text-emerald-700" : "text-rose-700"
          }`}
        >
          {formatNaira(totals.net)}
        </div>
      </div>
      <div className="rounded-2xl border border-gray-400 p-4 ">
        <div className="text-sm text-gray-500">Balance Checks Passed</div>
        <div className="text-xl font-semibold">{(totals.passRatio * 100).toFixed(1)}%</div>
      </div>
    </div>
  );
}
