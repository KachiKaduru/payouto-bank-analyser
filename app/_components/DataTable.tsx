import { ParsedRow } from "../_types";

interface DataTableProps {
  data: ParsedRow[];
}

export default function DataTable({ data }: DataTableProps) {
  const headers: (keyof ParsedRow)[] = [
    "TXN DATE",
    "VAL DATE",
    "REFERENCE",
    "REMARKS",
    "DEBIT",
    "CREDIT",
    "BALANCE",
    "Check",
    "Check 2",
  ];

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full bg-white border border-gray-200">
        <thead>
          <tr className="bg-gray-200">
            {headers.map((header) => (
              <th key={header} className="px-4 py-2 text-left text-sm font-semibold text-gray-700">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr key={index} className="border-t">
              {headers.map((header) => (
                <td key={header} className="px-4 py-2 text-sm text-gray-600">
                  {row[header] || "-"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
