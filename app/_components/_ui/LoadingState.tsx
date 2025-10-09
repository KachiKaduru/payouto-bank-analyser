"use client";

import { Tab } from "@/app/_types";
import { ArrowPathIcon } from "@heroicons/react/24/outline";
import { motion } from "framer-motion";

interface LoadingStateProps {
  currentTab: Tab;
  text?: string;
}

export default function LoadingState({ currentTab, text = "Loading data…" }: LoadingStateProps) {
  return (
    <section className="flex flex-col items-center justify-center h-full p-10 text-center bg-gradient-to-b from-white to-blue-50 rounded-2xl border border-blue-100 shadow-inner">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="flex flex-col items-center gap-6"
      >
        {/* Rotating icon */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{
            repeat: Infinity,
            duration: 1.4,
            ease: "linear",
          }}
          className="p-4 bg-blue-100 rounded-full"
        >
          <ArrowPathIcon className="w-8 h-8 text-blue-600" />
        </motion.div>

        {/* Title */}
        <h1 className="text-xl font-bold text-blue-800 capitalize">Loading {currentTab}…</h1>

        {/* Optional description */}
        {text && <p className="text-gray-600 max-w-md">{text}</p>}

        {/* Skeleton shimmer placeholder */}
        <div className="mt-6 w-full max-w-md space-y-3">
          {[...Array(3)].map((_, i) => (
            <div
              key={i}
              className="h-4 bg-gradient-to-r from-gray-200 via-gray-100 to-gray-200 rounded-lg animate-[shimmer_1.6s_infinite]"
            />
          ))}
        </div>
      </motion.div>

      {/* Shimmer animation keyframes */}
      <style jsx>{`
        @keyframes shimmer {
          0% {
            background-position: -200px 0;
          }
          100% {
            background-position: 200px 0;
          }
        }
        .animate-[shimmer_1.6s_infinite] {
          background-size: 400px 100%;
        }
      `}</style>
    </section>
  );
}
