"use client";

import { useMemo } from "react";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ScriptableContext,
  type TooltipItem,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { formatTimePeriod } from "@/app/_utils/helpers";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export default function DebitCreditChart() {
  const buckets = useAnalysisStore((s) => s.buckets);
  const chartData = useMemo(() => {
    if (!buckets?.length) return { labels: [], datasets: [] };

    // Format labels like "2024-06" -> "Jun 2024"
    const labels = buckets.map((b) => formatTimePeriod(b.label));

    const debitValues = buckets.map((b) => b.debit || 0);
    const creditValues = buckets.map((b) => b.credit || 0);

    const allValues = [...debitValues, ...creditValues];
    const minValue = Math.min(...allValues);
    const maxValue = Math.max(...allValues);

    // Approximate step size (5 intervals)
    const stepSize = Math.ceil((maxValue - minValue) / 5 / 1000) * 1000;

    const data = {
      labels,
      datasets: [
        {
          label: "Debits",
          data: debitValues,
          borderColor: "#ef4444", // red-500

          backgroundColor: (context: ScriptableContext<"line">) => {
            const ctx = context.chart.ctx;
            const gradient = ctx.createLinearGradient(0, 0, 0, context.chart.height);
            gradient.addColorStop(0, "rgba(239, 68, 68, 0.3)");
            gradient.addColorStop(1, "rgba(239, 68, 68, 0.05)");
            return gradient;
          },
          fill: true,
          tension: 0.1,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
        {
          label: "Credits",
          data: creditValues,
          borderColor: "#10b981", // green-500
          backgroundColor: (context: ScriptableContext<"line">) => {
            const ctx = context.chart.ctx;
            const gradient = ctx.createLinearGradient(0, 0, 0, context.chart.height);
            gradient.addColorStop(0, "rgba(16, 185, 129, 0.3)");
            gradient.addColorStop(1, "rgba(16, 185, 129, 0.05)");
            return gradient;
          },
          fill: true,
          tension: 0.1,
          pointRadius: 4,
          pointHoverRadius: 6,
        },
      ],
    };

    const options = {
      responsive: true,
      interaction: { mode: "index" as const, intersect: false },
      plugins: {
        legend: {
          display: true,
          position: "top" as const,
          labels: { usePointStyle: true, padding: 20 },
        },
        tooltip: {
          callbacks: {
            // Show debitCount or creditCount on hover
            afterLabel: function (context: TooltipItem<"line">) {
              const bucket = buckets[context.dataIndex];
              if (context.dataset.label === "Debits" && bucket.debitCount !== undefined) {
                return `Debit Count: ${bucket.debitCount}`;
              }
              if (context.dataset.label === "Credits" && bucket.creditCount !== undefined) {
                return `Credit Count: ${bucket.creditCount}`;
              }
              return undefined;
            },
          },
        },
      },
      scales: {
        x: {
          grid: { display: false },
        },
        y: {
          beginAtZero: true,
          ticks: { stepSize },
          grid: {
            color: "#f3f4f6",
            borderDash: [4, 4],
          },
        },
      },
    };

    return { data, options };
  }, [buckets]);

  if (!chartData?.data?.labels?.length) {
    return <p className="text-gray-500 text-center mt-8">No data available</p>;
  }

  return <Line data={chartData.data} options={chartData.options} />;
}
