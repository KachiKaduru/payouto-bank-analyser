import { useMemo } from "react";
import { useParserStore } from "../../_store/useParserStore";
import ExportExcelButton from "./ExportExcelButton";

export default function Stats() {
  const data = useParserStore((s) => s.data);
  const noOfErrorRows = useMemo(() => data.filter((row) => row.Check === "FALSE").length, [data]);

  if (data.length <= 0) return null;

  return (
    <section>
      <div className="my-6 flex gap-6 flex-wrap">
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

        <ExportExcelButton />
      </div>
    </section>
  );
}
