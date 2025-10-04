"use client";

import { useParserStore } from "./_store/useParserStore";

import PageHeader from "./_components/PageHeader";
import UploadForm from "./_components/UploadForm";
import ErrorSection from "./_components/ErrorSection";
import Tabs from "./_components/Tabs";

import TableData from "./_components/table/TableData";
import AnalysisSection from "./_components/analysis/AnalysisSection";

export default function Home() {
  const activeTab = useParserStore((s) => s.activeTab);

  return (
    <main className="min-h-[100dvh] bg-gradient-to-b from-blue-50 via-white to-blue-100 p-6">
      <section className="max-w-7xl mx-auto">
        <PageHeader />
        <UploadForm />
        <ErrorSection />

        <Tabs />

        <TableData className={activeTab === "table" ? "block" : "hidden"} />

        <AnalysisSection className={activeTab === "analysis" ? "block" : "hidden"} />
      </section>
    </main>
  );
}
