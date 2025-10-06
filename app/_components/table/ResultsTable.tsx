import React from "react";
import { useParserStore } from "../../_store/useParserStore";

function Table() {
  const data = useParserStore((s) => s.data);

  if (data.length <= 0) return null;

  return (
    <section className="overflow-auto border border-gray-200 shadow-md w-full max-h-[80dvh]">
      <table className="min-w-[1000px] text-sm border-collapse w-full">
        <thead className="bg-blue-100 sticky top-0 z-10">
          <tr>
            {Object.keys(data[0]).map((key) => (
              <th key={key} className="border p-3 text-center font-semibold text-blue-900">
                {key}
              </th>
            ))}
          </tr>
        </thead>

        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              className={
                row.Check === "FALSE" ? "bg-red-100" : i % 2 === 0 ? "bg-white" : "bg-gray-100"
              }
            >
              {Object.values(row).map((val, j) => (
                <td key={j} className="border p-3 max-w-[400px] overflow-hidden text-ellipsis">
                  {val}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
const ResultsTable = React.memo(Table);

export default ResultsTable;
