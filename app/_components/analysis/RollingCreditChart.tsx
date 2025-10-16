// app/_components/analysis/RollingCreditChart.tsx
"use client";

import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatNaira } from "@/app/_utils/helpers";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";

export default function RollingCreditChart() {
  const rc = useAnalysisStore((s) => s.rollingCredit);

  const data = [
    { label: "30 Days", Total: rc.total30, Average: rc.avg30 },
    { label: "90 Days", Total: rc.total90, Average: rc.avg90 },
    { label: "180 Days", Total: rc.total180, Average: rc.avg180 },
    { label: "6-Month Mean", Total: rc.combinedAvg, Average: rc.combinedAvg },
  ];

  return (
    <section className="rounded-3xl border border-blue-100 bg-gradient-to-b from-white to-blue-50 p-6 space-y-3 shadow-sm">
      <h2 className="text-lg font-bold text-blue-900">Rolling Credit Overview</h2>
      <p className="text-sm text-gray-600">
        Shows how total and per-month credit values evolve across 30, 90 and 180 days.
      </p>

      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
          <XAxis dataKey="label" />
          <YAxis tickFormatter={(v) => formatNaira(v)} width={80} />
          <Tooltip
            formatter={(v: number) => formatNaira(v)}
            contentStyle={{ borderRadius: "0.75rem" }}
          />
          <Legend />
          <Bar dataKey="Total" fill="#60a5fa" radius={[6, 6, 0, 0]} />
          <Bar dataKey="Average" fill="#3b82f6" radius={[6, 6, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </section>
  );
}
