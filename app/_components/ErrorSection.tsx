"use client";

import { useState, useMemo } from "react";
import { ExclamationTriangleIcon, ChevronDownIcon } from "@heroicons/react/24/outline";
import { useParserStore } from "../_store/useParserStore";

export default function ErrorSection() {
  const error = useParserStore((s) => s.error);
  const [showDetails, setShowDetails] = useState(false);

  // Extract the most relevant final line (e.g. "Error: ...")
  const summary = useMemo(() => {
    const lines = error.split("\n").filter(Boolean);
    const lastErrorLine =
      lines.find((l) => l.toLowerCase().startsWith("error:")) || lines[lines.length - 1];
    return lastErrorLine?.trim() || "An unknown error occurred.";
  }, [error]);

  if (!error) return null;

  return (
    <section className="w-full my-6">
      <div className="rounded-2xl border border-red-200 bg-gradient-to-br from-red-50 to-white shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-red-100">
          <ExclamationTriangleIcon className="w-6 h-6 text-red-600 flex-shrink-0" />
          <div>
            <h2 className="text-red-700 font-semibold">Parsing Error</h2>
            <p className="text-sm text-gray-700">{summary}</p>
          </div>
        </div>

        {/* Toggle button */}
        <button
          onClick={() => setShowDetails((v) => !v)}
          className="flex items-center justify-between w-full px-5 py-3 text-sm text-gray-600 bg-gray-50 hover:bg-gray-100 transition"
        >
          <span className="font-medium">{showDetails ? "Hide" : "View full"} details</span>
          <ChevronDownIcon
            className={`w-5 h-5 transform transition-transform ${showDetails ? "rotate-180" : ""}`}
          />
        </button>

        {/* Error details */}
        {showDetails && (
          <pre className="px-5 py-4 text-sm font-medium text-gray-700 bg-white max-h-96 overflow-y-auto whitespace-pre-wrap font-mono">
            {formatLog(error)}
          </pre>
        )}
      </div>
    </section>
  );
}

/**
 * Highlight common keywords for readability
 */
function formatLog(log: string): string {
  return log
    .replace(/(Error: .+)/g, "❌ $1")
    .replace(/\((\w+ parser)\)/g, "🔹 ($1)")
    .replace(/Processing page (\d+)/g, "📄 Processing page $1")
    .replace(/No headers found/g, "⚠️ No headers found");
}
