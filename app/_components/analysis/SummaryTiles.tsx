import { useAnalysisStore } from "@/app/_store/useAnalysisStore";

export default function SummaryTiles() {
  const totals = useAnalysisStore((s) => s.totals);

  if (totals.credit === 0 && totals.debit === 0) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
      <div className="rounded-2xl border p-4">
        <div className="text-sm text-gray-500">Total Credit</div>
        <div className="text-xl font-semibold">
          ₦{totals.credit.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </div>
      </div>
      <div className="rounded-2xl border p-4">
        <div className="text-sm text-gray-500">Total Debit</div>
        <div className="text-xl font-semibold">
          ₦{totals.debit.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </div>
      </div>
      <div className="rounded-2xl border p-4">
        <div className="text-sm text-gray-500">Net</div>
        <div
          className={`text-xl font-semibold ${
            totals.net >= 0 ? "text-emerald-700" : "text-rose-700"
          }`}
        >
          ₦{totals.net.toLocaleString(undefined, { maximumFractionDigits: 2 })}
        </div>
      </div>
      <div className="rounded-2xl border p-4">
        <div className="text-sm text-gray-500">Balance Checks Passed</div>
        <div className="text-xl font-semibold">{(totals.passRatio * 100).toFixed(1)}%</div>
      </div>
    </div>
  );
}
