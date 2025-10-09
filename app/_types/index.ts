export type Tab = "table" | "analysis" | "metadata" | "results";

export interface ParsedRow {
  TXN_DATE: string;
  VAL_DATE: string;
  REFERENCE: string;
  REMARKS: string;
  DEBIT: string;
  CREDIT: string;
  BALANCE: string;
  Check: string;
  "Check 2": string;
}

export interface StatementMeta {
  bank?: string | null;
  account_name?: string | null;
  account_number?: string | null;
  currency?: string | null;
  account_type?: string | null;
  start_date?: string | null; // ISO: YYYY-MM-DD
  end_date?: string | null; // ISO: YYYY-MM-DD
  opening_balance?: string | null; // "12345.67"
  closing_balance?: string | null;
  current_balance?: string | null;
  date_printed?: string | null; // ISO if we can normalize
  period_text?: string | null; // raw period header if present
  raw_header?: string | null; // first-page raw text slice used
}

export interface LegitimacyCheck {
  id: string;
  ok: boolean;
  severity: "info" | "warn" | "fail";
  message: string;
  details?: Record<string, unknown>;
}

export interface ParseResponse {
  meta: StatementMeta;
  transactions: ParsedRow[];
  checks: LegitimacyCheck[];
}
