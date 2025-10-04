import { useParserStore } from "@/app/_store/useParserStore";
import { ParsedRow } from "@/app/_types";
import { ArrowDownTrayIcon } from "@heroicons/react/16/solid";
import * as XLSX from "xlsx";

export default function ExportExcelButton() {
  const { data, file } = useParserStore();

  const handleExport = () => {
    if (data.length === 0) return;
    const headers = Object.keys(data[0]);
    const worksheetData = [
      headers,
      ...data.map((row) => headers.map((header) => row[header as keyof ParsedRow])),
    ];
    const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Bank Statement");

    const originalName = file?.name || "bank_statement.pdf";
    const excelName = originalName.replace(/\.pdf$/i, "") + ".xlsx";

    XLSX.writeFile(workbook, excelName);
  };

  return (
    <button
      type="button"
      onClick={handleExport}
      className="bg-green-600 text-white px-3 py-2 flex gap-2 rounded-lg hover:bg-green-700 ml-auto"
    >
      <ArrowDownTrayIcon className="w-5 h-5" />
      <span>Export as Excel</span>
    </button>
  );
}
