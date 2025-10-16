// app/_components/analysis/RollingCreditTiles.tsx
"use client";

import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatNaira } from "@/app/_utils/helpers";

export default function RollingCreditTiles() {
  const rc = useAnalysisStore((s) => s.rollingCredit);

  return (
    <>
      <h1>Credit Value Overview Per Month</h1>
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="rounded-2xl border border-gray-300 p-4">
          <div className="text-xs text-gray-500">Last 30 days (30d)</div>
          <div className="text-lg font-semibold">{formatNaira(rc.total30)}</div>
          <div className="text-[11px] text-gray-500 mt-1">Avg/30d: {formatNaira(rc.avg30)}</div>
        </div>
        <div className="rounded-2xl border border-gray-300 p-4">
          <div className="text-xs text-gray-500">Total Credit (90d)</div>
          <div className="text-lg font-semibold">{formatNaira(rc.total90)}</div>
          <div className="text-[11px] text-gray-500 mt-1">Avg/30d: {formatNaira(rc.avg90)}</div>
        </div>
        <div className="rounded-2xl border border-gray-300 p-4">
          <div className="text-xs text-gray-500">Total Credit (180d)</div>
          <div className="text-lg font-semibold">{formatNaira(rc.total180)}</div>
          <div className="text-[11px] text-gray-500 mt-1">Avg/30d: {formatNaira(rc.avg180)}</div>
        </div>
        <div className="rounded-2xl  p-4 md:col-span-2 bg-blue-50 border border-blue-100">
          <div className="text-xs text-blue-700">Six-Month Monthly Average (Mean of 30/90/180)</div>
          <div className="text-2xl font-bold text-blue-900">{formatNaira(rc.combinedAvg)}</div>
          <div className="text-[11px] text-blue-700 mt-1">
            = ( {formatNaira(rc.avg30)} + {formatNaira(rc.avg90)} + {formatNaira(rc.avg180)} ) ÷ 3
          </div>
        </div>
      </div>
    </>
  );
}
