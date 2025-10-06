"use client";

import { useEffect, useMemo } from "react";
import { useParserStore } from "../../_store/useParserStore";
import { useAnalysisStore } from "@/app/_store/useAnalysisStore";

import EmptyState from "../EmptyState";
import FilterControls from "./FilterControls";
import SummaryTiles from "./SummaryTiles";
import BucketsTable from "./BucketsTable";
import SummaryTable from "./SummaryTable";

export default function AnalysisSection({ className = "" }) {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

  const setRaw = useAnalysisStore((s) => s.setRaw);
  const filtered = useAnalysisStore((s) => s.filtered);

  useEffect(() => {
    setRaw(data || []);
  }, [data, setRaw]);

  const topCredits = useMemo(() => {
    return [...filtered]
      .map((r) => ({ ...r, _credit: Number((r.CREDIT || "0").replace(/[₦,\s]/g, "")) }))
      .sort((a, b) => b._credit - a._credit)
      .slice(0, 10);
  }, [filtered]);

  const topDebits = useMemo(() => {
    return [...filtered]
      .map((r) => ({ ...r, _debit: Number((r.DEBIT || "0").replace(/[₦,\s]/g, "")) }))
      .sort((a, b) => b._debit - a._debit)
      .slice(0, 10);
  }, [filtered]);

  if (loading && activeTab === "analysis") {
    return (
      <section className="border border-gray-300 rounded-xl w-full h-full p-6 animate-pulse">
        <h1 className="text-lg font-semibold mb-4">Analysis</h1>
        <p>Crunching numbers…</p>
      </section>
    );
  }

  if (data.length === 0 && activeTab === "analysis") return <EmptyState section="analysis" />;

  return (
    <section
      className={`border border-gray-200 p-6 rounded-2xl space-y-6 bg-white/70 ${className}`}
    >
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Analysis</h1>
        <span className="text-sm text-gray-500">
          {filtered.length.toLocaleString()} rows in view
        </span>
      </div>

      <FilterControls />

      <SummaryTiles />

      <BucketsTable />

      <div className="grid grid-cols-1 gap-6">
        <SummaryTable data={topCredits} title="credit" property="CREDIT" />
        <SummaryTable data={topDebits} title="debit" property="DEBIT" />
      </div>
    </section>
  );
}
