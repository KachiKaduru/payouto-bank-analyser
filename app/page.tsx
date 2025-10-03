"use client";

import UploadForm from "./_components/UploadForm";

import ErrorSection from "./_components/ErrorSection";
import Tabs from "./_components/Tabs";
import { useParserStore } from "./_store/useParserStore";
import Analysis from "./_components/Analysis";
import TableData from "./_components/TableData";
import PageHeader from "./_components/PageHeader";
// import LoadingPage from "./_components/LoadingPage";

export default function Home() {
  const activeTab = useParserStore((s) => s.activeTab);

  return (
    <main className="min-h-[100dvh] bg-gradient-to-b from-blue-50 via-white to-blue-100 p-6">
      <section className="max-w-7xl mx-auto">
        <PageHeader />
        <UploadForm />
        <ErrorSection />

        <div className="">
          <Tabs />

          <TableData className={activeTab === "table" ? "block" : "hidden"} />

          <Analysis className={activeTab === "analysis" ? "block" : "hidden"} />
        </div>
      </section>

      {/* <LoadingPage /> */}
    </main>
  );
}
