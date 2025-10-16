export type RangePreset = "last30" | "last60" | "last90" | "last180" | "all" | "custom";
export type SortKey = "none" | "largestCredit" | "largestDebit" | "txnDateAsc" | "txnDateDesc";
export type BucketMode = "none" | "monthly" | "biMonthly" | "quarterly";

export interface AnalysisFilters {
  preset: RangePreset;
  customFrom?: string; // YYYY-MM-DD
  customTo?: string; // YYYY-MM-DD
  search: string; // REMARKS/REFERENCE
  sortBy: SortKey;
  bucket: BucketMode;
}
export interface Bucket {
  label: string;
  debit: number;
  credit: number;
  net: number;
  rows: number;
  debitCount?: number;
  creditCount?: number;
}

export interface RollingCredit {
  total30: number;
  total90: number;
  total180: number;
  avg30: number; // per-30-day average over last 30d (i.e., total30 / 1)
  avg90: number; // per-30-day average over last 90d (i.e., total90 / 3)
  avg180: number; // per-30-day average over last 180d (i.e., total180 / 6)
  combinedAvg: number; // mean of (avg30, avg90, avg180)
}
