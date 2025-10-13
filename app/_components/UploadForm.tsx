"use client";

import { useParserStore } from "../_store/useParserStore";
import { banksList } from "../_constants";
import { useUploadHandler } from "../_hooks/useUploadHandler";
import {
  ArrowUpOnSquareIcon,
  LockClosedIcon,
  DocumentArrowUpIcon,
  MagnifyingGlassIcon,
  DocumentCheckIcon,
} from "@heroicons/react/24/outline";
import { useState, useTransition } from "react";
import { motion, AnimatePresence } from "framer-motion";

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
    <section className="max-w-7xl mx-auto">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleUpload();
        }}
        className="bg-gradient-to-b from-white to-blue-50 border border-blue-100 rounded-3xl shadow-sm p-8 space-y-6 transition"
      >
        <header className="text-center space-y-1">
          <h2 className="text-2xl font-bold text-blue-900">Upload your bank statement</h2>
          <p className="text-gray-500 text-sm">
            Supported formats: <span className="font-medium text-gray-700">PDF</span>
          </p>
        </header>

        {/* Step 1 — Select Bank */}
        <div>
          <label className="block text-base font-medium text-gray-700 m-2">Search for a bank</label>
          <div
            className="relative w-full border border-gray-300 rounded-xl flex items-center px-3 bg-white text-gray-800
  focus-within:border-blue-400 focus-within:ring-2 focus-within:ring-blue-200 transition"
          >
            <MagnifyingGlassIcon className="w-5 h-5 ml-3 text-gray-400 pointer-events-none" />

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
              placeholder="e.g Access Bank, GTBank, First Bank..."
              className="p-3 w-full outline-none"
            />

            <AnimatePresence>
              {search && (
                <motion.ul
                  initial={{ opacity: 0, y: -5 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -5 }}
                  className="absolute left-0 right-0 top-12 bg-white border border-gray-200 mt-1 max-h-48 overflow-y-auto rounded-xl shadow-lg z-20"
                >
                  {filteredBanks.length ? (
                    filteredBanks.map((bankOption) => (
                      <li
                        key={bankOption.value}
                        onClick={() => {
                          setBank(bankOption.value);
                          setDisplayedBank(bankOption.label);
                          setSearch("");
                        }}
                        className="px-4 py-2.5 hover:bg-blue-50 cursor-pointer transition text-gray-800"
                      >
                        {bankOption.label}
                      </li>
                    ))
                  ) : (
                    <li className="px-4 py-2 text-gray-500">No banks found</li>
                  )}
                </motion.ul>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Step 2 — Upload File */}
        <div className="relative">
          <div
            {...getRootProps()}
            className={`border-2 border-dashed rounded-2xl p-14 text-center transition cursor-pointer flex flex-col items-center justify-center ${
              isDragActive
                ? "border-blue-500 bg-blue-50"
                : "border-gray-300 bg-gray-50 hover:bg-gray-100"
            }`}
          >
            <input {...getInputProps()} />
            {file ? (
              <div className="flex items-center gap-2 text-green-700 font-medium">
                <DocumentCheckIcon className="w-5 h-5" />
                <span>
                  Selected: <span className="text-blue-900 font-semibold">{file.name}</span>
                </span>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 text-gray-600">
                <DocumentArrowUpIcon className="w-10 h-10 text-gray-400" />
                <p className="text-sm">
                  {isDragActive
                    ? "Drop your PDF here"
                    : "Drag & drop your statement, or click to browse"}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* Step 3 — Password-protected file */}
        <AnimatePresence>
          {showPasswordInput && (
            <motion.div
              initial={{ opacity: 0, y: -5 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -5 }}
              className="flex flex-col sm:flex-row gap-3 items-center bg-yellow-50 border border-yellow-200 p-4 rounded-xl"
            >
              <div className="flex items-center gap-2 text-yellow-800 font-semibold">
                <LockClosedIcon className="w-5 h-5" />
                <span>Encrypted PDF detected</span>
              </div>
              <input
                type="text"
                value={password}
                onChange={(e) => startTransition(() => setPassword(e.target.value))}
                placeholder="Enter PDF password"
                className="border border-gray-300 p-3 rounded-lg flex-1 focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
              <button
                type="button"
                onClick={handleRetryWithPassword}
                disabled={!password || loading}
                className="bg-blue-700 text-white px-6 py-2.5 rounded-lg disabled:opacity-50 hover:bg-blue-800 transition"
              >
                {loading ? "Decrypting..." : "Decrypt & Parse"}
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Step 4 — Submit */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={!file || !bank || loading || showPasswordInput}
            className="bg-blue-700 text-white px-6 py-3 rounded-xl font-semibold disabled:opacity-50 hover:bg-blue-800 transition flex items-center gap-2 shadow-sm"
          >
            <ArrowUpOnSquareIcon className="w-5 h-5" />
            {loading ? "Parsing..." : "Upload & Parse"}
          </button>
        </div>
      </form>
    </section>
  );
}
