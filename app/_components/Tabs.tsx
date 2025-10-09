"use client";

import { useParserStore } from "../_store/useParserStore";
import { motion } from "framer-motion";
import { Tab } from "../_types";

const buttonStyles = "px-6 py-3 font-semibold text-base transition w-full relative z-10";

export default function Tabs() {
  const activeTab = useParserStore((s) => s.activeTab);
  const setActiveTab = useParserStore((s) => s.setActiveTab);

  const tabs: Tab[] = ["table", "metadata", "analysis", "results"];
  const activeIndex = tabs.indexOf(activeTab);

  return (
    <section className="my-6 bg-gray-100">
      <div className="flex">
        {tabs.map((tab) => (
          <TabButton
            key={tab}
            tab={tab}
            isActive={activeTab === tab}
            handleTabChange={setActiveTab}
          />
        ))}
      </div>

      {/* Sliding indicator */}
      <div className="relative w-full h-1.5 overflow-hidden">
        <motion.div
          className="absolute left-0 bottom-0 h-1.5 bg-blue-700 rounded-full"
          style={{ width: `${100 / tabs.length}%` }}
          animate={{ x: `${100 * activeIndex}%` }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
        />
      </div>
    </section>
  );
}

function TabButton({
  tab,
  isActive,
  handleTabChange,
}: {
  tab: Tab;
  isActive: boolean;
  handleTabChange: (tab: Tab) => void;
}) {
  return (
    <button
      onClick={() => handleTabChange(tab)}
      className={`${buttonStyles} ${isActive ? "text-blue-700" : "text-gray-700"}`}
    >
      {tab.charAt(0).toUpperCase() + tab.slice(1)}
    </button>
  );
}
