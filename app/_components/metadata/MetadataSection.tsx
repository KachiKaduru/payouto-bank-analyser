"use client";

import { useParserStore } from "@/app/_store/useParserStore";
import { formatNaira, parseMoney } from "@/app/_utils/helpers";
import { motion } from "framer-motion";
import EmptyState from "../_ui/EmptyState";
import LoadingState from "../_ui/LoadingState";

export default function MetadataSection() {
  const meta = useParserStore((s) => s.meta);
  const checks = useParserStore((s) => s.checks);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

  console.log("Metadata:", meta);
  console.log("Legitimacy Checks:", checks);

  if (loading && activeTab === "metadata") {
    return <LoadingState currentTab="metadata" text="Fetching the data…" />;
  }

  if (!meta) return <EmptyState section="metadata" />;

  return (
    <section className="space-y-8 rounded-2xl bg-white/70">
      {/* Header */}
      <div className="text-center">
        <h1 className="text-2xl font-bold text-blue-900">Statement Metadata</h1>
        <p className="text-gray-500 text-sm">
          Overview of account details, summary, and validation checks
        </p>
      </div>

      {/* Metadata Grid */}
      <motion.div
        layout
        className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4 bg-white rounded-2xl shadow-sm p-6"
      >
        <MetaItem label="Account Name" value={meta.account_name} />
        <MetaItem label="Account Number" value={meta.account_number} />
        <MetaItem label="Currency" value={meta.currency} />
        <MetaItem label="Account Type" value={meta.account_type} />
        <MetaItem label="Period" value={meta.period_text || "N/A"} />
        <MetaItem label="Bank" value={meta.bank || "Unknown"} />
      </motion.div>

      {/* Summary Section */}
      <div className="bg-blue-50 rounded-2xl p-6 grid sm:grid-cols-3 gap-4">
        <SummaryCard title="Opening Balance" amount={meta.opening_balance} color="text-green-700" />
        <SummaryCard title="Closing Balance" amount={meta.closing_balance} color="text-blue-700" />
        <SummaryCard
          title="Current Balance"
          amount={meta.current_balance}
          color="text-purple-700"
        />
      </div>

      {/* Checks Section */}
      <div>
        <h2 className="text-lg font-semibold text-blue-800 mb-2">Validation Checks</h2>
        <ul className="divide-y divide-gray-200 bg-white rounded-xl shadow-sm">
          {checks?.map((check) => (
            <li
              key={check.id}
              className="flex justify-between items-start p-4 hover:bg-gray-50 transition"
            >
              <div>
                <p className="font-medium text-gray-800">{check.message}</p>
                {check.details && (
                  <pre className="text-xs text-gray-500 mt-1">
                    {JSON.stringify(check.details, null, 2)}
                  </pre>
                )}
              </div>
              <span
                className={`px-3 py-1 text-xs font-semibold rounded-full ${
                  check.ok
                    ? "bg-green-100 text-green-700"
                    : check.severity === "fail"
                    ? "bg-red-100 text-red-700"
                    : "bg-yellow-100 text-yellow-700"
                }`}
              >
                {check.severity.toUpperCase()}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/* Subcomponents */

function MetaItem({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div>
      <p className="text-sm text-gray-500">{label}</p>
      <p className="text-base font-semibold text-gray-800">{value || "—"}</p>
    </div>
  );
}

function SummaryCard({
  title,
  amount,
  color,
}: {
  title: string;
  amount: string | number | null | undefined;
  color?: string;
}) {
  return (
    <div className="bg-white rounded-xl shadow-sm p-4 text-center border border-blue-100">
      <p className="text-sm text-gray-600">{title}</p>
      <p className={`text-xl font-bold ${color || "text-gray-800"}`}>
        {formatNaira(parseMoney(amount))}
      </p>
    </div>
  );
}
