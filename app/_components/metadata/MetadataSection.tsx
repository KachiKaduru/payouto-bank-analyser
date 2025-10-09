"use client";

import { useParserStore } from "@/app/_store/useParserStore";
import { formatNaira, parseMoney } from "@/app/_utils/helpers";
import { motion } from "framer-motion";
import EmptyState from "../_ui/EmptyState";
import LoadingState from "../_ui/LoadingState";
import {
  BanknotesIcon,
  IdentificationIcon,
  InformationCircleIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";

export default function MetadataSection() {
  const meta = useParserStore((s) => s.meta);
  const checks = useParserStore((s) => s.checks);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

  if (loading && activeTab === "metadata") {
    return <LoadingState currentTab="metadata" text="Fetching metadata details…" />;
  }

  if (!meta) return <EmptyState section="metadata" />;

  return (
    <motion.section
      layout
      className="space-y-10 bg-gradient-to-b from-white to-blue-50 rounded-3xl shadow-sm p-6 sm:p-8 border border-blue-100"
    >
      {/* Header */}
      <header className="text-center space-y-2">
        <h1 className="text-2xl font-bold text-blue-900">Statement Metadata</h1>
        <p className="text-gray-600 text-sm">
          Overview of your account information, summary, and validation checks
        </p>
      </header>

      {/* Metadata Grid */}
      <motion.div
        layout
        className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 bg-white rounded-2xl p-6 shadow-inner"
      >
        <MetaItem label="Account Name" value={meta.account_name} />
        <MetaItem label="Account Number" value={meta.account_number} />
        <MetaItem label="Currency" value={meta.currency} />
        <MetaItem label="Account Type" value={meta.account_type} />
        <MetaItem label="Statement Period" value={meta.period_text || "N/A"} />
        <MetaItem label="Bank" value={meta.bank || "Unknown"} />
      </motion.div>

      {/* Summary Cards */}
      <div className="grid sm:grid-cols-3 gap-4">
        <SummaryCard
          title="Opening Balance"
          amount={meta.opening_balance}
          color="from-green-100 to-green-50 text-green-700"
          icon={<BanknotesIcon className="w-6 h-6 text-green-600" />}
        />
        <SummaryCard
          title="Closing Balance"
          amount={meta.closing_balance}
          color="from-blue-100 to-blue-50 text-blue-700"
          icon={<ShieldCheckIcon className="w-6 h-6 text-blue-600" />}
        />
        <SummaryCard
          title="Current Balance"
          amount={meta.current_balance}
          color="from-purple-100 to-purple-50 text-purple-700"
          icon={<InformationCircleIcon className="w-6 h-6 text-purple-600" />}
        />
      </div>

      {/* Checks Section */}
      <div>
        <h2 className="text-lg font-semibold text-blue-800 mb-4 flex items-center gap-2">
          <IdentificationIcon className="w-5 h-5 text-blue-600" />
          Validation Checks
        </h2>

        <ul className="divide-y divide-gray-200 bg-white rounded-2xl shadow-sm overflow-hidden">
          {checks?.map((check) => (
            <motion.li
              layout
              key={check.id}
              className="flex justify-between items-start p-4 hover:bg-blue-50/40 transition-colors"
            >
              <div className="flex-1 pr-4">
                <p className="font-medium text-gray-800">{check.message}</p>
                {check.details && (
                  <pre className="text-xs text-gray-500 mt-1 bg-gray-50 rounded-lg p-2 overflow-auto max-h-32">
                    {JSON.stringify(check.details, null, 2)}
                  </pre>
                )}
              </div>

              <span
                className={`px-3 py-1 text-xs font-semibold rounded-full self-start ${
                  check.ok
                    ? "bg-green-100 text-green-700"
                    : check.severity === "fail"
                    ? "bg-red-100 text-red-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {check.severity.toUpperCase()}
              </span>
            </motion.li>
          ))}
        </ul>
      </div>
    </motion.section>
  );
}

/* Subcomponents */

function MetaItem({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-base font-semibold text-gray-800 truncate">{value || "—"}</p>
    </div>
  );
}

function SummaryCard({
  title,
  amount,
  color,
  icon,
}: {
  title: string;
  amount: string | number | null | undefined;
  color?: string;
  icon?: React.ReactNode;
}) {
  return (
    <div
      className={`bg-gradient-to-b ${color} rounded-2xl p-5 text-center border border-blue-100 flex flex-col items-center gap-2`}
    >
      {icon}
      <p className="text-sm text-gray-700">{title}</p>
      <p className={`text-xl font-bold`}>{formatNaira(parseMoney(amount))}</p>
    </div>
  );
}
