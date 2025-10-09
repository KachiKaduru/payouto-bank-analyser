"use client";

import { DocumentArrowUpIcon } from "@heroicons/react/24/outline";
import { motion } from "framer-motion";

export default function EmptyState({ section = "analysis" }: { section: string }) {
  return (
    <section className="flex flex-col items-center justify-center h-full p-10 text-center bg-gradient-to-b from-white to-blue-50 rounded-2xl border border-dashed border-blue-200 shadow-inner">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center gap-4"
      >
        {/* Icon */}
        <motion.div
          animate={{
            y: [0, -5, 0],
          }}
          transition={{
            repeat: Infinity,
            duration: 2,
            ease: "easeInOut",
          }}
          className="relative"
        >
          <div className="p-4 bg-blue-100 rounded-full border border-blue-200">
            <DocumentArrowUpIcon className="w-10 h-10 text-blue-600" />
          </div>
          <span className="absolute inset-0 blur-xl bg-blue-400/30 rounded-full" />
        </motion.div>

        {/* Text */}
        <h1 className="text-2xl font-semibold text-blue-800">No data yet</h1>
        <p className="text-gray-600 max-w-md">
          Upload a bank statement to see the{" "}
          <span className="font-medium text-blue-700">{section}</span> here.
        </p>

        {/* Optional gentle CTA */}
        <button
          disabled
          className="mt-5 px-6 py-2 bg-blue-200/60 text-blue-700 font-medium rounded-full cursor-not-allowed"
        >
          Waiting for upload…
        </button>
      </motion.div>
    </section>
  );
}
