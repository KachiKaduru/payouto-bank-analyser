import { useDropzone } from "react-dropzone";
import { useParserStore } from "../_store/useParserStore";
import type { ParseResponse } from "../_types";

export function useUploadHandler() {
  const {
    file,
    bank,
    password,
    showPasswordInput,
    setFile,
    setData,
    setMeta,
    setChecks,
    setError,
    setLoading,
    setShowPasswordInput,
  } = useParserStore();

  // dropzone
  const onDrop = (acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"] },
    multiple: false,
  });

  // handle upload
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
    setShowPasswordInput(false);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("bank", bank);
      if (showPasswordInput && password) {
        formData.append("password", password);
      }

      const res = await fetch("/api/parse", {
        method: "POST",
        body: formData,
      });

      const json = (await res.json()) as ParseResponse | { error?: string };

      if (!res.ok) {
        const errMsg = (json as any)?.error || "Failed to parse file. Unknown error.";
        if (typeof errMsg === "string" && errMsg.includes("Please provide a password")) {
          setShowPasswordInput(true);
          setError(errMsg);
        } else {
          throw new Error(errMsg);
        }
        return;
      }

      const data = json as ParseResponse;
      setData(data.transactions || []);
      setMeta(data.meta || null);
      setChecks(data.checks || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
      setData([]);
      setMeta(null);
      setChecks([]);
    } finally {
      setLoading(false);
    }
  };

  const handleRetryWithPassword = () => {
    if (password && showPasswordInput) {
      handleUpload();
    }
  };

  return {
    file,
    getRootProps,
    getInputProps,
    isDragActive,
    handleUpload,
    handleRetryWithPassword,
  };
}
