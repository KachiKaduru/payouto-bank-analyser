"use client";

import { useEffect, useMemo } from "react";
import { useParserStore } from "../_store/useParserStore";
import { BucketMode, RangePreset, SortKey, useAnalysisStore } from "../_store/useAnalysisStore";
import EmptyState from "./EmptyState";

export default function Analysis({ className = "" }) {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

  const { setRaw, setFilters, filters, totals, buckets, filtered } = useAnalysisStore();

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

  if (loading) {
    return (
      <section className="border border-gray-300 rounded-xl w-full h-full p-6 animate-pulse">
        <h1 className="text-lg font-semibold mb-4">Analysis</h1>
        <p>Crunching numbers…</p>
      </section>
    );
  }

  if ((!data || data.length === 0) && activeTab === "analysis") {
    return <EmptyState section="analysis" />;
  }

  return (
    <section
      className={`"border border-gray-300 p-6 rounded-2xl space-y-6 bg-white/40 ${className}`}
    >
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold">Analysis</h1>
        <span className="text-sm text-gray-500">
          {filtered.length.toLocaleString()} rows in view
        </span>
      </div>

      {/* Controls */}
      <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Preset */}
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Range</span>
          <select
            className="w-full border rounded-xl px-3 py-2"
            value={filters.preset}
            onChange={(e) => setFilters({ preset: e.target.value as RangePreset })}
          >
            <option value="last30">Last 30 days</option>
            <option value="last60">Last 60 days</option>
            <option value="last90">Last 90 days</option>
            <option value="all">All</option>
            <option value="custom">Custom…</option>
          </select>
        </label>

        {filters.preset === "custom" && (
          <>
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">From</span>
              <input
                type="date"
                className="w-full border rounded-xl px-3 py-2"
                value={filters.customFrom || ""}
                onChange={(e) => setFilters({ customFrom: e.target.value })}
              />
            </label>
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">To</span>
              <input
                type="date"
                className="w-full border rounded-xl px-3 py-2"
                value={filters.customTo || ""}
                onChange={(e) => setFilters({ customTo: e.target.value })}
              />
            </label>
          </>
        )}

        {/* Buckets */}
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Bucket</span>
          <select
            className="w-full border rounded-xl px-3 py-2"
            value={filters.bucket}
            onChange={(e) => setFilters({ bucket: e.target.value as BucketMode })}
          >
            <option value="monthly">Monthly</option>
            <option value="biMonthly">Every 2 months</option>
            <option value="quarterly">Quarterly</option>
            <option value="none">None</option>
          </select>
        </label>

        {/* Sort */}
        <label className="text-sm">
          <span className="block text-gray-600 mb-1">Sort</span>
          <select
            className="w-full border rounded-xl px-3 py-2"
            value={filters.sortBy}
            onChange={(e) => setFilters({ sortBy: e.target.value as SortKey })}
          >
            <option value="none">None</option>
            <option value="largestCredit">Largest credit</option>
            <option value="largestDebit">Largest debit</option>
            <option value="txnDateAsc">Oldest first</option>
            <option value="txnDateDesc">Newest first</option>
          </select>
        </label>

        {/* Search */}
        <label className="text-sm md:col-span-2 lg:col-span-2">
          <span className="block text-gray-600 mb-1">Search (REMARKS / REFERENCE)</span>
          <input
            type="text"
            placeholder="e.g. levy, airtime, loan, POS, transfer to..."
            className="w-full border rounded-xl px-3 py-2"
            value={filters.search}
            onChange={(e) => setFilters({ search: e.target.value })}
          />
        </label>
      </div>

      {/* Summary tiles */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="rounded-2xl border p-4">
          <div className="text-sm text-gray-500">Total Credit</div>
          <div className="text-xl font-semibold">
            ₦{totals.credit.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="rounded-2xl border p-4">
          <div className="text-sm text-gray-500">Total Debit</div>
          <div className="text-xl font-semibold">
            ₦{totals.debit.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="rounded-2xl border p-4">
          <div className="text-sm text-gray-500">Net</div>
          <div
            className={`text-xl font-semibold ${
              totals.net >= 0 ? "text-emerald-700" : "text-rose-700"
            }`}
          >
            ₦{totals.net.toLocaleString(undefined, { maximumFractionDigits: 2 })}
          </div>
        </div>
        <div className="rounded-2xl border p-4">
          <div className="text-sm text-gray-500">Balance Checks Passed</div>
          <div className="text-xl font-semibold">{(totals.passRatio * 100).toFixed(1)}%</div>
        </div>
      </div>

      {/* Buckets table */}
      <div className="rounded-2xl border overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-gray-600">
            <tr>
              <th className="text-left px-4 py-3">Bucket</th>
              <th className="text-right px-4 py-3">Credit</th>
              <th className="text-right px-4 py-3">Debit</th>
              <th className="text-right px-4 py-3">Net</th>
              <th className="text-right px-4 py-3">Rows</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((b) => (
              <tr key={b.label} className="border-t">
                <td className="px-4 py-2">{b.label}</td>
                <td className="px-4 py-2 text-right">₦{b.credit.toLocaleString()}</td>
                <td className="px-4 py-2 text-right">₦{b.debit.toLocaleString()}</td>
                <td
                  className={`px-4 py-2 text-right ${
                    b.net >= 0 ? "text-emerald-700" : "text-rose-700"
                  }`}
                >
                  ₦{b.net.toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right">{b.rows.toLocaleString()}</td>
              </tr>
            ))}
            {!buckets.length && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-gray-500">
                  No data in the current view.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Top 10 lists */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl border overflow-x-auto">
          <div className="px-4 py-3 border-b font-semibold">Top 10 Credits</div>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2">TXN DATE</th>
                <th className="text-left px-4 py-2">REMARKS</th>
                <th className="text-right px-4 py-2">CREDIT</th>
                <th className="text-left px-4 py-2">REFERENCE</th>
              </tr>
            </thead>
            <tbody>
              {topCredits.map((r, i) => (
                <tr key={i} className="border-t">
                  <td className="px-4 py-2">{r["TXN DATE"]}</td>
                  <td className="px-4 py-2 max-w-[26rem] truncate" title={r.REMARKS}>
                    {r.REMARKS}
                  </td>
                  <td className="px-4 py-2 text-right">{r.CREDIT}</td>
                  <td className="px-4 py-2">{r.REFERENCE}</td>
                </tr>
              ))}
              {!topCredits.length && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                    No credits found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="rounded-2xl border overflow-x-auto">
          <div className="px-4 py-3 border-b font-semibold">Top 10 Debits</div>
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-gray-600">
              <tr>
                <th className="text-left px-4 py-2">TXN DATE</th>
                <th className="text-left px-4 py-2">REMARKS</th>
                <th className="text-right px-4 py-2">DEBIT</th>
                <th className="text-left px-4 py-2">REFERENCE</th>
              </tr>
            </thead>
            <tbody>
              {topDebits.map((r, i) => (
                <tr key={i} className="border-t">
                  <td className="px-4 py-2">{r["TXN DATE"]}</td>
                  <td className="px-4 py-2 max-w-[26rem] truncate" title={r.REMARKS}>
                    {r.REMARKS}
                  </td>
                  <td className="px-4 py-2 text-right">{r.DEBIT}</td>
                  <td className="px-4 py-2">{r.REFERENCE}</td>
                </tr>
              ))}
              {!topDebits.length && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-gray-500">
                    No debits found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
