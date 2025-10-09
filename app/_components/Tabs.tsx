"use client";

import { useParserStore } from "../_store/useParserStore";
import { motion } from "framer-motion";
import { Tab } from "../_types";

export default function Tabs() {
  const activeTab = useParserStore((s) => s.activeTab);
  const setActiveTab = useParserStore((s) => s.setActiveTab);

  const tabs: Tab[] = ["table", "metadata", "analysis", "results"];
  const activeIndex = tabs.indexOf(activeTab);

  return (
    <section className="my-6 border-b border-gray-200">
      <div className="flex justify-around relative">
        {tabs.map((tab) => {
          const isActive = activeTab === tab;
          return (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`relative px-4 py-3 font-medium capitalize transition-colors duration-200 ${
                isActive ? "text-blue-700" : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {tab}
            </button>
          );
        })}

        {/* Active underline */}
        <motion.div
          className="absolute bottom-0 left-0 h-[4px] bg-blue-600 rounded-full"
          style={{ width: `${100 / tabs.length}%` }}
          animate={{ x: `${100 * activeIndex}%` }}
          transition={{
            type: "spring",
            stiffness: 300,
            damping: 30,
          }}
        />
      </div>
    </section>
  );
}
