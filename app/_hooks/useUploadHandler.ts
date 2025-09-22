import { useDropzone } from "react-dropzone";
import { useParserStore } from "../_store/useParserStore";

export function useUploadHandler() {
  const {
    file,
    bank,
    password,
    showPasswordInput,
    setFile,
    setData,
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
