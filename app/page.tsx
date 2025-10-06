"use client";

import PageHeader from "./_components/PageHeader";
import UploadForm from "./_components/UploadForm";
import ErrorSection from "./_components/ErrorSection";
import Tabs from "./_components/Tabs";
import DisplayDataSection from "./_components/DisplayDataSection";
// import LoadingSpinner from "./_components/_ui/LoadingSpinner";

export default function Home() {
  return (
    <main className="min-h-[100dvh] bg-gradient-to-b from-blue-50 via-white to-blue-100 p-6">
      <section className="max-w-7xl min-w-2xl mx-auto">
        <PageHeader />
        <UploadForm />
        <ErrorSection />

        <Tabs />

        {/* <LoadingSpinner /> */}

        <DisplayDataSection />
      </section>
    </main>
  );
}
