import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import { BucketMode, RangePreset, SortKey } from "@/app/_types/analysis-types";

export default function FilterControls() {
  //   const filters = useAnalysisStore((s) => s.filters);
  //   const setFilters = useAnalysisStore((s) => s.setFilters);

  const { filters, setFilters } = useAnalysisStore();

  return (
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
  );
}
