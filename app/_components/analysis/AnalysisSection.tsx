"use client";

import { useEffect, useMemo } from "react";
import { useParserStore } from "../../_store/useParserStore";
import { useAnalysisStore } from "@/app/_store/useAnalysisStore";

import EmptyState from "../_ui/EmptyState";
import LoadingState from "../_ui/LoadingState";
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
      .map((r) => ({
        ...r,
        _credit: Number((r.CREDIT || "0").replace(/[₦,\s]/g, "")),
      }))
      .sort((a, b) => b._credit - a._credit)
      .slice(0, 10);
  }, [filtered]);

  const topDebits = useMemo(() => {
    return [...filtered]
      .map((r) => ({
        ...r,
        _debit: Number((r.DEBIT || "0").replace(/[₦,\s]/g, "")),
      }))
      .sort((a, b) => b._debit - a._debit)
      .slice(0, 10);
  }, [filtered]);

  if (loading && activeTab === "analysis")
    return <LoadingState currentTab="analysis" text="Crunching numbers…" />;

  if (data.length === 0 && activeTab === "analysis") return <EmptyState section="analysis" />;

  return (
    <section
      className={`space-y-8 bg-gradient-to-b from-white to-blue-50 rounded-3xl shadow-sm p-6 sm:p-8 border border-blue-100 ${className}`}
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-blue-900">Analysis</h1>
        <span className="text-sm text-gray-500">
          {filtered.length.toLocaleString()} rows in view
        </span>
      </div>

      {/* Filters */}
      <FilterControls />

      {/* Summary */}
      <SummaryTiles />

      {/* Buckets */}
      <BucketsTable />

      {/* Top Transactions */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <SummaryTable data={topCredits} title="Credit" property="CREDIT" />
        <SummaryTable data={topDebits} title="Debit" property="DEBIT" />
      </div>
    </section>
  );
}
