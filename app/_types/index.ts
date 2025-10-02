export interface RowData {
  date: string;
  description: string;
  amount: string;
  balance: string;
}

export interface ParsedRow {
  "TXN DATE": string;
  "VAL DATE": string;
  REFERENCE: string;
  REMARKS: string;
  DEBIT: string;
  CREDIT: string;
  BALANCE: string;
  Check: string;
  "Check 2": string;
}

export type Tab = "table" | "analysis";
