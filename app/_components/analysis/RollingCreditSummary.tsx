// app/_components/analysis/RollingCreditSummary.tsx
"use client";

import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatNaira } from "@/app/_utils/helpers";

export default function RollingCreditSummary() {
  const rc = useAnalysisStore((s) => s.rollingCredit);

  return (
    <section className="rounded-3xl bg-gradient-to-r from-blue-50 to-blue-100 border border-blue-200 p-6 shadow-sm">
      <h2 className="text-lg font-bold text-blue-900 mb-2">Credit Activity Snapshot</h2>
      <p className="text-gray-700 text-sm leading-relaxed">
        In the last <strong>30 days</strong>, this account recorded total credits of
        <strong> {formatNaira(rc.total30)}</strong>. Over <strong>90 days</strong>, that rises to{" "}
        <strong>{formatNaira(rc.total90)}</strong>—an average of{" "}
        <strong>{formatNaira(rc.avg90)}</strong> per month. In the last <strong>180 days</strong>,
        credits totaled <strong>{formatNaira(rc.total180)}</strong>, averaging{" "}
        <strong>{formatNaira(rc.avg180)}</strong> per month. <br />
        Overall, the estimated monthly credit inflow for the past six months is{" "}
        <strong className="text-blue-900">{formatNaira(rc.combinedAvg)}</strong>.
      </p>
    </section>
  );
}
