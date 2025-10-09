"use client";

import { useParserStore } from "@/app/_store/useParserStore";
import EmptyState from "../_ui/EmptyState";
import LoadingState from "../_ui/LoadingState";
import { motion } from "framer-motion";
import { SparklesIcon } from "@heroicons/react/24/outline";

export default function ResultsSection() {
  const data = useParserStore((s) => s.data);
  const loading = useParserStore((s) => s.loading);
  const activeTab = useParserStore((s) => s.activeTab);

  if (loading && activeTab === "results") {
    return <LoadingState currentTab="results" text="Getting the best offer based on the data…" />;
  }

  if (data.length === 0 && activeTab === "results") return <EmptyState section="results" />;

  return (
    <section className="flex flex-col items-center justify-center text-center h-full p-10 bg-gradient-to-b from-white to-blue-50 rounded-2xl border border-blue-100 shadow-inner">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center gap-4"
      >
        <div className="relative">
          <SparklesIcon className="w-16 h-16 text-blue-600 animate-pulse" />
          <span className="absolute inset-0 blur-xl bg-blue-400/30 rounded-full" />
        </div>
        <h1 className="text-2xl font-bold text-blue-800">Results Section Coming Soon</h1>
        <p className="text-gray-600 max-w-md">
          We&apos;re working on something exciting — this section will soon provide intelligent
          insights and performance summaries based on your parsed statement data.
        </p>
        <button
          disabled
          className="mt-4 px-6 py-2 bg-blue-200 text-blue-700 font-medium rounded-full cursor-not-allowed"
        >
          Stay Tuned
        </button>
      </motion.div>
    </section>
  );
}
