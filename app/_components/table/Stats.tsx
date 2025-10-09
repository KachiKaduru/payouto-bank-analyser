import { useMemo } from "react";
import { useParserStore } from "../../_store/useParserStore";
import ExportExcelButton from "./ExportExcelButton";
import { EyeIcon, EyeSlashIcon } from "@heroicons/react/24/outline";

export default function Stats() {
  const data = useParserStore((s) => s.data);
  const viewFailedRows = useParserStore((s) => s.viewFailedRows);
  const setViewFailedRows = useParserStore((s) => s.setViewFailedRows);
  const noOfErrorRows = useMemo(() => data.filter((row) => row.Check === "FALSE").length, [data]);

  function handleFailedRowsDisplay() {
    setViewFailedRows(!viewFailedRows);
  }

  if (data.length <= 0) return null;

  return (
    <section>
      <div className="flex gap-6 flex-wrap">
        <div className="bg-blue-100 text-blue-800 px-4 py-2 rounded-lg font-semibold">
          Total Rows: {data.length}
        </div>
        <div
          className={`px-4 py-2 rounded-lg font-semibold ${
            noOfErrorRows > 0
              ? noOfErrorRows < 10
                ? "bg-amber-100 text-amber-800"
                : "bg-red-100 text-red-800"
              : "bg-green-100 text-green-800"
          }`}
        >
          Failed Rows: {noOfErrorRows}
        </div>

        {noOfErrorRows > 0 && (
          <button
            onClick={handleFailedRowsDisplay}
            className="p-2 font-semibold bg-gray-200 flex gap-2 items-center rounded-xl"
          >
            {viewFailedRows ? (
              <EyeSlashIcon className="w-5 h-5" />
            ) : (
              <EyeIcon className="w-5 h-5" />
            )}
            <p>View {viewFailedRows ? "All" : "Failed"} Rows</p>
          </button>
        )}
        <ExportExcelButton />
      </div>
    </section>
  );
}
