import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatMonthYear, formatNaira } from "@/app/_utils/helpers";

export default function BucketsTable() {
  const buckets = useAnalysisStore((s) => s.buckets);

  return (
    <div className="rounded-2xl border overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="text-left px-4 py-3">Bucket</th>
            <th className="text-right px-4 py-3">Credit</th>
            <th className="text-right px-4 py-3">Debit</th>
            <th className="text-right px-4 py-3">Net</th>
            <th className="text-right px-4 py-3">Credit Count</th>
            <th className="text-right px-4 py-3">Debit Count</th>
            <th className="text-right px-4 py-3">Rows</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((b) => (
            <tr key={b.label} className="border-t">
              <td className="px-4 py-2">{formatMonthYear(b.label)}</td>
              <td className="px-4 py-2 text-right">{formatNaira(b.credit)}</td>
              <td className="px-4 py-2 text-right">{formatNaira(b.debit)}</td>
              <td
                className={`px-4 py-2 text-right ${
                  b.net >= 0 ? "text-emerald-700" : "text-rose-700"
                }`}
              >
                {formatNaira(b.net)}
              </td>
              <td className="px-4 py-2 text-right">{b.creditCount}</td>
              <td className="px-4 py-2 text-right">{b.debitCount}</td>
              <td className="px-4 py-2 text-right">{b.rows.toLocaleString()}</td>
            </tr>
          ))}
          {!buckets.length && (
            <tr>
              <td colSpan={5} className="px-4 py-6 text-center text-gray-500">
                No data in the current view.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
