"use client";

import { useState } from "react";

interface PdfUploadProps {
  onParsed: (data: any[]) => void;
}

export default function PdfUpload({ onParsed }: PdfUploadProps) {
  const [loading, setLoading] = useState(false);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);

    const res = await fetch("/upload", {
      method: "POST",
      body: formData,
    });

    const result = await res.json();
    setLoading(false);
    onParsed(result.rows);
  };

  return (
    <div className="mb-6">
      <input
        type="file"
        accept="application/pdf"
        onChange={handleUpload}
        className="file-input file-input-bordered"
      />
      {loading && <p className="mt-2 text-blue-600">Parsing PDF...</p>}
    </div>
  );
}
