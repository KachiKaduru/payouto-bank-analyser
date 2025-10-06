// app/_store/useParserStore.ts
import { create } from "zustand";
import { ParsedRow, Tab } from "../_types";

interface ParserState {
  file: File | null;
  bank: string;
  data: ParsedRow[];
  loading: boolean;
  error: string;
  password: string;
  showPasswordInput: boolean;

  activeTab: Tab;
  viewFailedRows: boolean;

  // actions
  setFile: (file: File | null) => void;
  setBank: (bank: string) => void;
  setData: (data: ParsedRow[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string) => void;
  setPassword: (password: string) => void;
  setShowPasswordInput: (show: boolean) => void;
  reset: () => void;

  setActiveTab: (tab: Tab) => void;
  setViewFailedRows: (view: boolean) => void;
}

export const useParserStore = create<ParserState>((set) => ({
  file: null,
  bank: "",
  data: [],
  loading: false,
  error: "",
  password: "",
  showPasswordInput: false,
  activeTab: "table",
  viewFailedRows: false,

  setFile: (file) => set({ file }),
  setBank: (bank) => set({ bank }),
  setData: (data) => set({ data }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setPassword: (password) => set({ password }),
  setShowPasswordInput: (show) => set({ showPasswordInput: show }),

  reset: () =>
    set({
      file: null,
      bank: "",
      data: [],
      loading: false,
      error: "",
      password: "",
      showPasswordInput: false,
    }),

  setActiveTab: (tab: Tab) => set({ activeTab: tab }),
  setViewFailedRows: (view) => set({ viewFailedRows: view }),
}));
