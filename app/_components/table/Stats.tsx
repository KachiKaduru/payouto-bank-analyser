"use client";

import { useMemo } from "react";
import { useParserStore } from "../../_store/useParserStore";
import ExportExcelButton from "./ExportExcelButton";
import {
  EyeIcon,
  EyeSlashIcon,
  TableCellsIcon,
  ExclamationTriangleIcon,
} from "@heroicons/react/24/outline";

export default function Stats() {
  const data = useParserStore((s) => s.data);
  const viewFailedRows = useParserStore((s) => s.viewFailedRows);
  const setViewFailedRows = useParserStore((s) => s.setViewFailedRows);
  const noOfErrorRows = useMemo(() => data.filter((row) => row.Check === "FALSE").length, [data]);

  if (data.length <= 0) return null;

  const totalRows = data.length;
  const errorRatio = ((noOfErrorRows / totalRows) * 100).toFixed(1);

  return (
    <div className="bg-white rounded-2xl border border-blue-100 shadow-sm p-5 flex flex-wrap items-center gap-4 justify-between">
      {/* Stats badges */}
      <div className="flex flex-wrap gap-3">
        <StatBadge
          icon={<TableCellsIcon className="w-5 h-5 text-blue-600" />}
          label="Total Rows"
          value={totalRows.toLocaleString()}
          color="text-blue-800"
          bg="bg-blue-100"
        />

        <StatBadge
          icon={<ExclamationTriangleIcon className="w-5 h-5 text-amber-600" />}
          label="Failed Rows"
          value={`${noOfErrorRows} (${errorRatio}%)`}
          color={
            noOfErrorRows > 0
              ? noOfErrorRows < 10
                ? "text-amber-700"
                : "text-red-700"
              : "text-green-700"
          }
          bg={
            noOfErrorRows > 0 ? (noOfErrorRows < 10 ? "bg-amber-50" : "bg-red-50") : "bg-green-50"
          }
        />
      </div>

      {/* Actions */}
      <div className="flex items-center gap-3">
        {noOfErrorRows > 0 && (
          <button
            onClick={() => setViewFailedRows(!viewFailedRows)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-gray-100 hover:bg-gray-200 font-medium text-gray-800 transition"
          >
            {viewFailedRows ? (
              <EyeSlashIcon className="w-5 h-5" />
            ) : (
              <EyeIcon className="w-5 h-5" />
            )}
            {viewFailedRows ? "View All Rows" : "View Failed Rows"}
          </button>
        )}

        <ExportExcelButton />
      </div>
    </div>
  );
}

/* Small subcomponent for reusable stat badge */
function StatBadge({
  icon,
  label,
  value,
  color,
  bg,
}: {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  color?: string;
  bg?: string;
}) {
  return (
    <div
      className={`flex items-center gap-2 px-4 py-2 rounded-xl border border-gray-200 ${bg} ${color} text-sm font-semibold`}
    >
      {icon}
      <div>
        <span className="block text-xs text-gray-500">{label}</span>
        <span className="text-base font-semibold">{value}</span>
      </div>
    </div>
  );
}
