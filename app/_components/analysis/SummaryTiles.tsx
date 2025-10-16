import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatNaira } from "@/app/_utils/helpers";

const Tile = ({
  title,
  value,
  color,
}: {
  title: string;
  value: string | number;
  color?: string;
}) => (
  <div className="bg-white border border-blue-100 rounded-2xl shadow-sm p-5 space-y-1">
    <p className="text-xs font-semibold text-gray-600">{title}</p>
    <p className={`text-[22px] font-bold ${color}`}>{value}</p>
  </div>
);

export default function SummaryTiles() {
  const totals = useAnalysisStore((s) => s.totals);
  if (totals.credit === 0 && totals.debit === 0) return null;

  return (
    <section className="space-y-4">
      <h1 className="font-semibold text-2xl capitalize text-blue-900">Total overview</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Tile title="Total Credit" value={formatNaira(totals.credit)} color="text-green-700" />
        <Tile title="Total Debit" value={formatNaira(totals.debit)} color="text-red-700" />
        <Tile
          title="Net"
          value={formatNaira(totals.net)}
          color={totals.net >= 0 ? "text-emerald-700" : "text-rose-700"}
        />
        <Tile
          title="Balance Checks Passed"
          value={`${(totals.passRatio * 100).toFixed(1)}%`}
          color="text-blue-700"
        />
      </div>
    </section>
  );
}
