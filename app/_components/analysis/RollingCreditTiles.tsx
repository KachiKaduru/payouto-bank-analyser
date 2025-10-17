// app/_components/analysis/RollingCreditTiles.tsx
"use client";

import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatNaira } from "@/app/_utils/helpers";

function Card({ title = "", totalValue = 0, avgValue = 0 }) {
  return (
    <div className="p-4 space-y-2 rounded-2xl border border-gray-300 ">
      <div className="text-xs font-semibold text-gray-500">{title}</div>
      <div className="text-2xl font-bold text-blue-950">{formatNaira(avgValue)}</div>
      <div className="text-[13px] text-blue-900 mt-1">
        Credit Value: <strong>{formatNaira(totalValue)}</strong>
      </div>
    </div>
  );
}

export default function RollingCreditTiles() {
  const rc = useAnalysisStore((s) => s.rollingCredit);

  return (
    <section className="space-y-4 mt-10">
      <h1 className="font-semibold text-2xl capitalize text-blue-900">
        Credit Value Overview Per Month
      </h1>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card title="Last 30 days" totalValue={rc.total30} avgValue={rc.avg30} />
        <Card title="Last 90 days " totalValue={rc.total90} avgValue={rc.avg90} />
        <Card title="Last 180 days" totalValue={rc.total180} avgValue={rc.avg180} />

        <div className="p-4 space-y-2 rounded-2xl  bg-blue-50 border border-blue-100">
          <div className="text-xs font-semibold text-blue-700">Monthly Average per 180 days</div>
          <div className="text-2xl font-bold text-blue-900">{formatNaira(rc.combinedAvg)}</div>
          <div className="text-[11px] text-blue-700 mt-1">
            = ( {formatNaira(rc.avg30)} + {formatNaira(rc.avg90)} + {formatNaira(rc.avg180)} ) ÷ 3
          </div>
        </div>
      </div>
    </section>
  );
}
