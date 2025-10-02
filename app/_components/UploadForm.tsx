import { useParserStore } from "../_store/useParserStore";
import { banksList } from "../_constants";
import { useUploadHandler } from "../_hooks/useUploadHandler";
import { ArrowUpOnSquareIcon, CheckCircleIcon } from "@heroicons/react/24/outline";
import { useState, useTransition } from "react";

export default function UploadForm() {
  const { file, bank, loading, password, showPasswordInput, setBank, setPassword } =
    useParserStore();

  const { handleUpload, getRootProps, getInputProps, isDragActive, handleRetryWithPassword } =
    useUploadHandler();

  const [, startTransition] = useTransition();
  const [search, setSearch] = useState("");
  const [displayedBank, setDisplayedBank] = useState("");

  const filteredBanks = banksList.filter((b) =>
    b.label.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <section>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleUpload();
        }}
        className="bg-white shadow-md rounded-xl p-6 space-y-4 border border-blue-100"
      >
        <h2 className="text-xl font-semibold text-blue-700">Step 1: Upload your statement</h2>

        {/* Bank Dropdown */}
        <div className="relative w-full max-w-[200px]">
          <input
            type="text"
            value={displayedBank}
            onChange={(e) => {
              startTransition(() => {
                setSearch(e.target.value);
                setDisplayedBank(e.target.value);

                if (e.target.value === "") setBank("");
              });
            }}
            placeholder="Search bank..."
            className="border p-3 rounded-lg w-full focus:outline-none focus:ring-2 focus:ring-blue-400"
          />

          {search && (
            <ul className="absolute left-0 right-0 bg-white border border-gray-200 mt-1 max-h-48 overflow-y-auto rounded-lg shadow-lg z-10">
              {filteredBanks.length ? (
                filteredBanks.map((bankOption) => (
                  <li
                    key={bankOption.value}
                    onClick={() => {
                      setBank(bankOption.value);
                      setDisplayedBank(bankOption.label);
                      setSearch("");
                    }}
                    className="px-3 py-2 hover:bg-blue-100 cursor-pointer"
                  >
                    {bankOption.label}
                  </li>
                ))
              ) : (
                <li className="px-3 py-2 text-gray-500">No banks found</li>
              )}
            </ul>
          )}
        </div>

        {/* Drag & Drop uploader */}
        <div
          {...getRootProps()}
          className={`border-2 border-dashed rounded-lg p-14 text-center transition cursor-pointer ${
            isDragActive
              ? "border-blue-500 bg-blue-50"
              : "border-gray-300 bg-gray-50 hover:bg-gray-100"
          }`}
        >
          <input {...getInputProps()} />
          {file ? (
            <p className="text-sm text-gray-700 flex justify-center gap-2">
              <CheckCircleIcon className="w-5 h-5 text-green-700" />
              <span>
                Selected: <strong className="text-blue-900">{file.name}</strong>
              </span>
            </p>
          ) : (
            <p className="text-gray-500">
              {isDragActive
                ? "Drop the PDF here..."
                : "Drag & drop your bank statement here, or click to browse"}
            </p>
          )}
        </div>

        {/* Password input (if needed) */}
        {showPasswordInput && (
          <div className="flex gap-3 items-center">
            <input
              type="text"
              value={password}
              onChange={(e) => {
                startTransition(() => setPassword(e.target.value));
              }}
              placeholder="Enter PDF password"
              className="border border-gray-300 p-3 rounded-lg flex-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <button
              type="button"
              onClick={handleRetryWithPassword}
              disabled={!password || loading}
              className="bg-blue-700 text-white px-6 py-2.5 rounded-lg disabled:opacity-50 hover:bg-blue-800"
            >
              {loading ? "Decrypting..." : "Decrypt & Parse"}
            </button>
          </div>
        )}

        {/* Submit button */}
        <div className="flex gap-4">
          <button
            type="submit"
            disabled={!file || !bank || loading || showPasswordInput}
            className="bg-blue-700 text-white px-6 py-2.5 rounded-lg disabled:opacity-50 hover:bg-blue-800 flex gap-2"
          >
            <ArrowUpOnSquareIcon className="w-5 h-5" />
            {loading ? "Parsing..." : "Upload & Parse"}
          </button>
        </div>
      </form>
    </section>
  );
}
