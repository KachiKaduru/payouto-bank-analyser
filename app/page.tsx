"use client";

import { DocumentTextIcon } from "@heroicons/react/16/solid";
import UploadForm from "./_components/UploadForm";
import Stats from "./_components/Stats";
import ResultsTable from "./_components/ResultsTable";
import ErrorSection from "./_components/ErrorSection";

export default function Home() {
  return (
    <main className="min-h-[100dvh] bg-gradient-to-b from-blue-50 via-white to-blue-100 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <h1 className="text-3xl font-bold text-blue-800 mb-6 text-center flex items-center justify-center">
          <DocumentTextIcon className="w-10 h-10" />
          <span>Bank Statement Parser</span>
        </h1>

        <UploadForm />

        <ErrorSection />

        <Stats />

        <ResultsTable />
      </div>
    </main>
  );
}
