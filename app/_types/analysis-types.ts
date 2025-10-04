export type RangePreset = "last30" | "last60" | "last90" | "all" | "custom";
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
  name: string; // e.g. "Jan 2023", "Q1 2023"
  from: string; // YYYY-MM-DD
  to: string; // YYYY-MM-DD
  totalCredit: number;
  totalDebit: number;
  net: number; // totalCredit - totalDebit
}
