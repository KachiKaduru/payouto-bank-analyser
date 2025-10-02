import Image from "next/image";
// import { DocumentTextIcon } from "@heroicons/react/16/solid";

export default function PageHeader() {
  return (
    <header>
      <h1 className="text-3xl font-bold text-blue-800 mb-6 text-center flex items-center justify">
        <div className="relative w-11 h-12 mr-3">
          <Image src="/images/payouto-icon.png" alt="" fill />
        </div>
        {/* <DocumentTextIcon className="w-10 h-10" /> */}
        <span>Bank Statement Parser</span>
      </h1>
    </header>
  );
}
