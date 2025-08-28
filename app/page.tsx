"use client";

import { useState } from "react";
import { ParsedRow } from "./_types";
import * as XLSX from "xlsx";
import { banksList } from "./_constants";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [bank, setBank] = useState<string>("");
  const [data, setData] = useState<ParsedRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [password, setPassword] = useState<string>("");
  const [showPasswordInput, setShowPasswordInput] = useState(false);

  const handleUpload = async () => {
    if (!file) {
      setError("No file uploaded");
      return;
    }
    if (!bank) {
      setError("Please select a bank");
      return;
    }
    setLoading(true);
    setError("");
    setShowPasswordInput(false); // Reset password input visibility

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("bank", bank); // Add bank to form data
      if (showPasswordInput && password) {
        formData.append("password", password);
      }

      const res = await fetch("/api/parse", {
        method: "POST",
        body: formData,
      });

      const result = await res.json();

      if (!res.ok) {
        if (result.error.includes("Please provide a password")) {
          setShowPasswordInput(true);
          setError(result.error);
        } else {
          throw new Error(result.error || "Failed to parse file.");
        }
      } else {
        setData(result || []);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  const handleRetryWithPassword = () => {
    if (password && showPasswordInput) {
      handleUpload(); // Retry with the entered password
    }
  };

  // 📦 Export with preserved column order
  const handleExport = () => {
    if (data.length === 0) return;

    // Get headers in the same order as displayed
    const headers = Object.keys(data[0]);

    // Convert JSON to array-of-arrays with headers first
    const worksheetData = [
      headers,
      ...data.map((row) => headers.map((header) => row[header as keyof ParsedRow])),
    ];

    // Create worksheet & workbook
    const worksheet = XLSX.utils.aoa_to_sheet(worksheetData);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Bank Statement");

    // Trigger download
    const originalName = file?.name || "bank_statement.pdf";
    const excelName = originalName.replace(/\.pdf$/i, "") + ".xlsx";

    XLSX.writeFile(workbook, excelName);
  };

  return (
    <div className="min-h-screen p-6 bg-gray-50">
      <h1 className="text-2xl font-bold mb-6">Bank Statement Parser</h1>

      <div className="flex gap-4 items-center mb-4">
        {/* Bank Dropdown */}
        <select
          value={bank}
          onChange={(e) => setBank(e.target.value)}
          className="border p-2 rounded-md w-[200px]"
          required
        >
          <option value="" disabled>
            Select Bank
          </option>
          {banksList.map((bankOption) => (
            <option key={bankOption.value} value={bankOption.value}>
              {bankOption.label}
            </option>
          ))}
        </select>

        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="border p-2 rounded-md file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-blue-500 file:text-white hover:file:bg-blue-600"
        />

        <button
          onClick={handleUpload}
          disabled={!file || !bank || loading || showPasswordInput}
          className="bg-blue-600 text-white px-4 py-2 rounded-md disabled:opacity-50 hover:bg-blue-700"
        >
          {loading ? "Parsing..." : "Upload & Parse"}
        </button>

        {showPasswordInput && (
          <div className="flex gap-4 items-center mb-4">
            <input
              type="text"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter PDF password"
              className="border p-2 rounded-md"
            />
            <button
              onClick={handleRetryWithPassword}
              disabled={!password || loading}
              className="bg-blue-600 text-white px-4 py-2 rounded-md disabled:opacity-50 hover:bg-blue-700"
            >
              {loading ? "Decrypting..." : "Decrypt & Parse"}
            </button>
          </div>
        )}

        {data.length > 0 && (
          <button
            onClick={handleExport}
            className="bg-green-600 text-white px-4 py-2 rounded-md hover:bg-green-700"
          >
            Export as Excel
          </button>
        )}
      </div>

      {error && <div className="text-red-500 font-medium mb-4">{error}</div>}

      {data.length > 0 && (
        <div className="overflow-auto border rounded-lg">
          <table className="min-w-[1000px] text-sm table-auto border-collapse">
            <thead className="bg-gray-200">
              <tr>
                {Object.keys(data[0]).map((key) => (
                  <th key={key} className="border p-2 whitespace-nowrap">
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.map((row, i) => (
                <tr
                  key={i}
                  className={
                    row.Check === "FALSE" ? "bg-red-100" : i % 2 === 0 ? "bg-white" : "bg-gray-50"
                  }
                >
                  {Object.values(row).map((val, j) => (
                    <td key={j} className="border p-2 max-w-[600px] overflow-ellipsis">
                      {val}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
