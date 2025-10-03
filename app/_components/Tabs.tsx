import { useParserStore } from "../_store/useParserStore";
import { motion } from "framer-motion";

// const activeClass = "bg-blue-600 text-white";
// const inactiveClass = "bg-gray-2000 text-gray-700 hover:bg-gray-3000";
const buttonStyles = "px-6 py-2 rounded-3xl font-medium transition w-full";

export default function Tabs() {
  const activeTab = useParserStore((s) => s.activeTab);
  const setActiveTab = useParserStore((s) => s.setActiveTab);

  const handleTabChange = (tab: "table" | "analysis") => setActiveTab(tab);

  return (
    <div className="flex my-6 p-1.5 bg-gray-200 rounded-3xl">
      <div className="inline-flex bg-gray-300 rounded-2xl w-full relative">
        <motion.div
          className="absolute top-0 left-0 bottom-0 w-1/2 bg-blue-600 rounded-3xl"
          animate={{
            x: activeTab === "table" ? "0%" : "100%",
          }}
          transition={{ type: "spring", stiffness: 300, damping: 30 }}
          initial={false}
        />
        <button
          onClick={() => handleTabChange("table")}
          className={`${buttonStyles} relative z-10 ${
            activeTab === "table" ? "text-white" : "text-gray-700"
          }`}
        >
          Table
        </button>
        <button
          onClick={() => handleTabChange("analysis")}
          className={`${buttonStyles} relative z-10 ${
            activeTab === "analysis" ? "text-white" : "text-gray-700"
          }`}
        >
          Analysis
        </button>
      </div>
    </div>
  );
}
