import { useAnalysisStore } from "@/app/_store/useAnalysisStore";
import {
  FunnelIcon,
  ClockIcon,
  ArrowDownTrayIcon,
  MagnifyingGlassIcon,
} from "@heroicons/react/24/outline";
import { BucketMode, RangePreset, SortKey } from "@/app/_types/analysis-types";

const controlClasses =
  "w-full border border-gray-300 bg-white rounded-xl px-3 py-2 focus:ring-2 focus:ring-blue-400 outline-none transition text-sm";

function ControlWrapper({
  label,
  icon,
  children,
}: {
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <label className="text-sm flex flex-col gap-1">
      <span className="text-gray-600 flex items-center gap-1">
        {icon && <span className="text-blue-600">{icon}</span>}
        {label}
      </span>
      {children}
    </label>
  );
}

export default function FilterControls() {
  const filters = useAnalysisStore((s) => s.filters);
  const setFilters = useAnalysisStore((s) => s.setFilters);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 lg:grid-cols-6 gap-4 bg-white p-4 rounded-2xl shadow-inner border border-blue-100">
      {/* Range */}
      <ControlWrapper label="Range" icon={<ClockIcon className="w-4 h-4" />}>
        <select
          className={controlClasses}
          value={filters.preset}
          onChange={(e) => setFilters({ preset: e.target.value as RangePreset })}
        >
          <option value="last30">Last 30 days</option>
          <option value="last60">Last 60 days</option>
          <option value="last90">Last 90 days</option>
          <option value="all">All</option>
          <option value="custom">Custom…</option>
        </select>
      </ControlWrapper>

      {filters.preset === "custom" && (
        <>
          <ControlWrapper label="From">
            <input
              type="date"
              className={controlClasses}
              value={filters.customFrom || ""}
              onChange={(e) => setFilters({ customFrom: e.target.value })}
            />
          </ControlWrapper>
          <ControlWrapper label="To">
            <input
              type="date"
              className={controlClasses}
              value={filters.customTo || ""}
              onChange={(e) => setFilters({ customTo: e.target.value })}
            />
          </ControlWrapper>
        </>
      )}

      {/* Bucket */}
      <ControlWrapper label="Bucket" icon={<FunnelIcon className="w-4 h-4" />}>
        <select
          className={controlClasses}
          value={filters.bucket}
          onChange={(e) => setFilters({ bucket: e.target.value as BucketMode })}
        >
          <option value="monthly">Monthly</option>
          <option value="biMonthly">Every 2 months</option>
          <option value="quarterly">Quarterly</option>
          <option value="none">None</option>
        </select>
      </ControlWrapper>

      {/* Sort */}
      <ControlWrapper label="Sort By" icon={<ArrowDownTrayIcon className="w-4 h-4" />}>
        <select
          className={controlClasses}
          value={filters.sortBy}
          onChange={(e) => setFilters({ sortBy: e.target.value as SortKey })}
        >
          <option value="none">None</option>
          <option value="largestCredit">Largest credit</option>
          <option value="largestDebit">Largest debit</option>
          <option value="txnDateAsc">Oldest first</option>
          <option value="txnDateDesc">Newest first</option>
        </select>
      </ControlWrapper>

      {/* Search */}
      <ControlWrapper label="Search" icon={<MagnifyingGlassIcon className="w-4 h-4" />}>
        <input
          type="text"
          placeholder="e.g. levy, airtime, POS..."
          className={controlClasses}
          value={filters.search}
          onChange={(e) => setFilters({ search: e.target.value })}
        />
      </ControlWrapper>
    </div>
  );
}
