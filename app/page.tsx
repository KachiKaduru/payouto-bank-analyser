"use client";

import { useState } from "react";
import { ParsedRow } from "./_types";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [data, setData] = useState<ParsedRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await fetch("/api/parse", {
        method: "POST",
        body: formData,
      });

      const result = await res.json();

      if (!res.ok) {
        throw new Error(result.error || "Failed to parse file.");
      }

      setData(result || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen p-6 bg-gray-50">
      <h1 className="text-2xl font-bold mb-6">Bank Statement Parser</h1>

      <div className="flex gap-4 items-center mb-4">
        <input
          type="file"
          accept="application/pdf"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="border p-2 rounded-md file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-blue-500 file:text-white hover:file:bg-blue-600"
        />
        <button
          onClick={handleUpload}
          disabled={!file || loading}
          className="bg-blue-600 text-white px-4 py-2 rounded-md disabled:opacity-50 hover:bg-blue-700"
        >
          {loading ? "Parsing..." : "Upload & Parse"}
        </button>
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
