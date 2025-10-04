import { ParsedRow } from "@/app/_types";
import { formatNaira } from "@/app/_utils/helpers";

interface SummaryTableProps {
  data: ParsedRow[];
  title: string;
  property?: "CREDIT" | "DEBIT";
}

export default function SummaryTable({ data, title, property = "CREDIT" }: SummaryTableProps) {
  return (
    <div className="rounded-2xl border overflow-x-auto">
      <div className="px-4 py-3 border-b font-semibold capitalize">Top 10 {title}s</div>
      <table className="min-w-full text-sm">
        <thead className="bg-gray-50 text-gray-600">
          <tr>
            <th className="text-left px-4 py-2">TXN_DATE</th>
            <th className="text-left px-4 py-2">REMARKS</th>
            <th className="text-right px-4 py-2">{property}</th>
            <th className="text-left px-4 py-2">REFERENCE</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r, i) => (
            <tr key={i} className="border-t">
              <td className="px-4 py-2 min-w-[7.5rem]">{r.TXN_DATE}</td>
              <td className="px-4 py-2 max-w-[26rem] truncate" title={r.REMARKS}>
                {r.REMARKS}
              </td>
              <td className="px-4 py-2 text-right">{formatNaira(r[`${property}`])}</td>
              <td className="px-4 py-2">{r.REFERENCE}</td>
            </tr>
          ))}
          {!data.length && (
            <tr>
              <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                No {title}s found.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
