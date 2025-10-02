// app/_lib/analysis.ts
import type { ParsedRow } from "../_types";

export type TxnType =
  | "TRANSFER_IN"
  | "TRANSFER_OUT"
  | "POS"
  | "LEVY"
  | "AIRTIME"
  | "DATA"
  | "SAVINGS"
  | "ELECTRICITY"
  | "MERCHANT"
  | "OTHER";

export interface DerivedTxn {
  date: string; // ISO
  valueDate: string;
  reference: string;
  remarks: string;
  debit: number;
  credit: number;
  balance: number | null;
  check: string;
  check2: string;
  type: TxnType;
  counterparty: string | null;
  channel: string | null; // lightweight inference when possible
}

export interface AnalysisOptions {
  start?: Date;
  end?: Date;
  monthBucket?: 1 | 2 | 3;
  minAmount?: number;
  types?: TxnType[]; // if provided, only include these
  keyword?: string;
}

export interface Totals {
  debit: number;
  credit: number;
  net: number; // credit - debit
}

export interface BalanceHealth {
  rows: number;
  passed: number; // "Check" true-ish
  passRate: number; // 0..1
}

export interface CounterpartyAgg {
  name: string;
  count: number;
  totalIn: number;
  totalOut: number;
}

export interface BucketSeries {
  label: string; // e.g. "2025-03"
  debit: number;
  credit: number;
  net: number;
  count: number;
}

export interface Extremes {
  topCredits: DerivedTxn[];
  topDebits: DerivedTxn[];
}

export interface AnalysisResult {
  rows: DerivedTxn[];
  totals: Totals;
  balanceHealth: BalanceHealth;
  byType: Record<TxnType, { count: number; debit: number; credit: number }>;
  byCounterpartyTopCount: CounterpartyAgg[]; // top by frequency
  byCounterpartyTopVolume: CounterpartyAgg[]; // top by abs(totalIn+totalOut)
  series: BucketSeries[];
  extremes: Extremes;
}

const money = (s: string): number => {
  if (!s) return 0;
  const n = s.replace(/[,\s₦]/g, "");
  const v = Number(n);
  return Number.isFinite(v) ? v : 0;
};

const numOrNull = (s: string): number | null => {
  if (!s) return null;
  const v = money(s);
  return Number.isFinite(v) ? v : null;
};

const toISO = (s: string): string => {
  // Assume parsers already normalize to YYYY-MM-DD where possible.
  // Fallback: let Date parse and reformat.
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const d = new Date(s);
  if (!isNaN(d.getTime())) return d.toISOString().slice(0, 10);
  return s; // give up; keeps original
};

const inferType = (r: ParsedRow): TxnType => {
  const t = `${r.REMARKS} ${r.REFERENCE}`.toLowerCase();

  if (/transfer\s+from|money received|receive/.test(t)) return "TRANSFER_IN";
  if (/transfer\s+to|send to/.test(t)) return "TRANSFER_OUT";
  if (/\bpos\b|card payment/.test(t)) return "POS";
  if (/levy|stamp duty/i.test(r.REMARKS)) return "LEVY";
  if (/airtime/.test(t)) return "AIRTIME";
  if (/\bdata\b/.test(t)) return "DATA";
  if (/owealth|savings|spend & save/.test(t)) return "SAVINGS";
  if (/electric/i.test(t)) return "ELECTRICITY";
  if (/merchant consumption/.test(t)) return "MERCHANT";
  return "OTHER";
};

const extractCounterparty = (remarks: string): string | null => {
  if (!remarks) return null;
  // Common “Transfer to X” / “Transfer from Y” / variants with new lines
  const s = remarks.replace(/\s+/g, " ");
  let m =
    /transfer\s+to\s+([^-\n\r|]+?)(?:\s*[-|]|$)/i.exec(s) ||
    /transfer\s+from\s+([^-\n\r|]+?)(?:\s*[-|]|$)/i.exec(s) ||
    /send\s+to\s+([^-\n\r|]+?)(?:\s*[-|]|$)/i.exec(s) ||
    /received\s+from\s+([^-\n\r|]+?)(?:\s*[-|]|$)/i.exec(s);

  if (m && m[1]) return m[1].trim();
  return null;
};

const extractChannel = (remarks: string): string | null => {
  const t = remarks.toLowerCase();
  if (/\be-channel\b/.test(t)) return "E-Channel";
  if (/\bpos\b|card payment/.test(t)) return "POS";
  return null;
};

export const toDerived = (rows: ParsedRow[]): DerivedTxn[] =>
  rows.map((r) => {
    const debit = money(r.DEBIT);
    const credit = money(r.CREDIT);
    const balance = numOrNull(r.BALANCE);
    const remarks = r.REMARKS ?? "";
    return {
      date: toISO(r["TXN DATE"] ?? r["TXN DATE"] ?? ""),
      valueDate: toISO(r["VAL DATE"] ?? r["VAL DATE"] ?? ""),
      reference: r.REFERENCE ?? "",
      remarks,
      debit,
      credit,
      balance,
      check: r.Check ?? "",
      check2: r["Check 2"] ?? "",
      type: inferType(r),
      counterparty: extractCounterparty(remarks),
      channel: extractChannel(remarks),
    };
  });

const within = (dISO: string, start?: Date, end?: Date) => {
  const d = new Date(dISO);
  if (isNaN(d.getTime())) return false;
  if (start && d < stripTime(start)) return false;
  if (end && d > endOfDay(end)) return false;
  return true;
};

const stripTime = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const endOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate(), 23, 59, 59, 999);

const passCheck = (s: string) => /^true$/i.test(String(s).trim());

export function analyze(rows: ParsedRow[], opts: AnalysisOptions = {}): AnalysisResult {
  const derived = toDerived(rows);

  // Filter by date
  const filteredByDate = derived.filter((x) => within(x.date || x.valueDate, opts.start, opts.end));

  // Filter by min amount
  const filteredByAmt = filteredByDate.filter((x) => {
    const amt = Math.max(x.credit, x.debit);
    return (opts.minAmount ?? 0) <= amt;
  });

  // Filter by types
  const filteredByType =
    opts.types && opts.types.length
      ? filteredByAmt.filter((x) => opts.types!.includes(x.type))
      : filteredByAmt;

  // Keyword filter
  const kw = (opts.keyword || "").trim().toLowerCase();
  const filtered =
    kw.length > 0
      ? filteredByType.filter(
          (x) =>
            x.remarks.toLowerCase().includes(kw) ||
            x.reference.toLowerCase().includes(kw) ||
            (x.counterparty || "").toLowerCase().includes(kw)
        )
      : filteredByType;

  // Totals
  const totals: Totals = filtered.reduce(
    (acc, x) => {
      acc.debit += x.debit;
      acc.credit += x.credit;
      return acc;
    },
    { debit: 0, credit: 0, net: 0 }
  );
  totals.net = totals.credit - totals.debit;

  // Balance health
  const health: BalanceHealth = {
    rows: filtered.length,
    passed: filtered.filter((x) => passCheck(x.check)).length,
    passRate: 0,
  };
  health.passRate = health.rows ? health.passed / health.rows : 0;

  // By type
  const byType = filtered.reduce((m, x) => {
    if (!m[x.type]) m[x.type] = { count: 0, debit: 0, credit: 0 };
    m[x.type].count++;
    m[x.type].debit += x.debit;
    m[x.type].credit += x.credit;
    return m;
  }, {} as Record<TxnType, { count: number; debit: number; credit: number }>);

  // Counterparties
  const cpAgg = new Map<string, CounterpartyAgg>();
  for (const x of filtered) {
    const k = (x.counterparty || "(unknown)").toUpperCase();
    const entry = cpAgg.get(k) || { name: k, count: 0, totalIn: 0, totalOut: 0 };
    entry.count++;
    entry.totalIn += x.credit;
    entry.totalOut += x.debit;
    cpAgg.set(k, entry);
  }
  const counterList = Array.from(cpAgg.values());
  const byCounterpartyTopCount = [...counterList].sort((a, b) => b.count - a.count).slice(0, 20);
  const byCounterpartyTopVolume = [...counterList]
    .sort((a, b) => b.totalIn + b.totalOut - (a.totalIn + a.totalOut))
    .slice(0, 20);

  // Series (month bucketing)
  const step = opts.monthBucket ?? 1; // 1=monthly, 2=2-month, 3=quarter
  const seriesMap = new Map<string, BucketSeries>();
  for (const x of filtered) {
    if (!x.date) continue;
    const d = new Date(x.date);
    const stepIndex = Math.floor(d.getMonth() / step) * step;
    const label = `${d.getFullYear()}-${String(stepIndex + 1).padStart(2, "0")}${
      step > 1 ? `..${String(stepIndex + step).padStart(2, "0")}` : ""
    }`;
    const s = seriesMap.get(label) || { label, debit: 0, credit: 0, net: 0, count: 0 };
    s.debit += x.debit;
    s.credit += x.credit;
    s.net = s.credit - s.debit;
    s.count++;
    seriesMap.set(label, s);
  }
  const series = [...seriesMap.values()].sort((a, b) => a.label.localeCompare(b.label));

  // Extremes
  const topCredits = [...filtered].sort((a, b) => b.credit - a.credit).slice(0, 20);
  const topDebits = [...filtered].sort((a, b) => b.debit - a.debit).slice(0, 20);

  return {
    rows: filtered,
    totals,
    balanceHealth: health,
    byType,
    byCounterpartyTopCount,
    byCounterpartyTopVolume,
    series,
    extremes: { topCredits, topDebits },
  };
}
