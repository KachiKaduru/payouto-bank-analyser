"use client";

import * as XLSX from "xlsx";
import { RowData } from "../_types";

interface Props {
  data: RowData[];
}

export default function ParsedTable({ data }: Props) {
  const exportToExcel = () => {
    const worksheet = XLSX.utils.json_to_sheet(data);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Statement");
    XLSX.writeFile(workbook, "statement.xlsx");
  };

  return (
    <div>
      <button onClick={exportToExcel} className="mb-4 bg-blue-500 text-white px-4 py-2 rounded">
        Export to Excel
      </button>
      <table className="w-full table-auto border border-gray-300">
        <thead>
          <tr className="bg-gray-100">
            <th className="border p-2">Date</th>
            <th className="border p-2">Description</th>
            <th className="border p-2">Amount</th>
            <th className="border p-2">Balance</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row, idx) => (
            <tr key={idx}>
              <td className="border p-2">{row.date}</td>
              <td className="border p-2">{row.description}</td>
              <td className="border p-2">{row.amount}</td>
              <td className="border p-2">{row.balance}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
