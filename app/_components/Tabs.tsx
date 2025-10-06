"use client";

import { useParserStore } from "../_store/useParserStore";
import { motion } from "framer-motion";
import { Tab } from "../_types";

const buttonStyles = "px-6 py-3 font-medium transition w-full relative z-10";

export default function Tabs() {
  const activeTab = useParserStore((s) => s.activeTab);
  const setActiveTab = useParserStore((s) => s.setActiveTab);

  const tabs: Tab[] = ["table", "analysis", "metadata"];
  const activeIndex = tabs.indexOf(activeTab);

  return (
    <div className="flex my-6 bg-gray-200/20 p-1">
      <div className="relative flex w-full overflow-hidden">
        {/* Sliding indicator */}
        <motion.div
          className="absolute left-0 bottom-0 h-1.5 bg-blue-600 rounded-full"
          style={{ width: `${100 / tabs.length}%` }}
          animate={{ x: `${100 * activeIndex}%` }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
        />

        {/* Tab Buttons */}
        {tabs.map((tab) => (
          <TabButton
            key={tab}
            tab={tab}
            isActive={activeTab === tab}
            handleTabChange={setActiveTab}
          />
        ))}
      </div>
    </div>
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
      className={`${buttonStyles} ${isActive ? "text-blue-800" : "text-gray-700"}`}
    >
      {tab.charAt(0).toUpperCase() + tab.slice(1)}
    </button>
  );
}
