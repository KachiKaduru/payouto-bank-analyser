import { useState } from "react";
import BucketsTable from "./BucketsTable";
import DebitCreditChart from "./DebitCreditChart";

type Btn = "chart" | "table";

function TabButton({ onClick, btn, view }: { onClick: () => void; btn: Btn; view: string }) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 rounded-md text-sm font-medium transition-all capitalize ${
        view === btn ? "bg-white text-blue-600 shadow-sm" : "text-gray-500 hover:text-gray-700"
      }`}
    >
      {btn}
    </button>
  );
}

export default function BucketsSection() {
  const [view, setView] = useState<Btn>("table");
  const btns: Btn[] = ["table", "chart"];

  function handleTabSwitch(tab: "chart" | "table") {
    setView(tab);
  }

  return (
    <section className="w-full bg-white rounded-xl shadow-sm border border-gray-100 p-4 md:p-6">
      {/* Tabs */}
      <div className="flex justify-center mb-6">
        <div className="inline-flex bg-gray-100 rounded-lg p-1">
          {btns.map((btn) => (
            <TabButton onClick={() => handleTabSwitch(btn)} btn={btn} key={btn} view={view} />
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="mt-4">
        {view === "chart" ? (
          <div className="h-[600px] grid place-content-center">
            <DebitCreditChart />
          </div>
        ) : (
          <BucketsTable />
        )}
      </div>
    </section>
  );
}
