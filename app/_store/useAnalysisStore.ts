import { create } from "zustand";
import { ParsedRow } from "../_types";

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

interface AnalysisState {
  raw: ParsedRow[];
  filtered: ParsedRow[];
  totals: {
    debit: number;
    credit: number;
    net: number;
    rows: number;
    passRatio: number;
  };
  buckets: Array<{ label: string; debit: number; credit: number; net: number; rows: number }>;
  /** uses classifyType so it's not unused and also gives quick breakdowns */
  typeSummary: Record<
    "transferIn" | "transferOut" | "pos" | "levy" | "airtime" | "data" | "other",
    {
      debit: number;
      credit: number;
      rows: number;
    }
  >;

  filters: AnalysisFilters;

  setRaw: (rows: ParsedRow[]) => void;
  setFilters: (patch: Partial<AnalysisFilters>) => void;
  recompute: () => void;
}

// ---------- helpers ----------
const parseMoney = (s: string | number | null | undefined): number => {
  if (!s) return 0;
  if (typeof s === "number") return s;
  const clean = s.replace(/[₦,\s]/g, "");
  const n = Number(clean);
  return Number.isFinite(n) ? n : 0;
};

// Robust date normalizer -> "YYYY-MM-DD" or null
const toISO = (s: string): string | null => {
  if (!s) return null;
  const str = s.trim();

  // Already ISO
  if (/^\d{4}-\d{2}-\d{2}$/.test(str)) return str;

  // e.g. 01/01/2025 or 01-01-2025
  let m = str.match(/\b(\d{2})[/-](\d{2})[/-](\d{4})\b/);
  if (m) {
    const [, d, mo, y] = m;
    return `${y}-${mo}-${d}`;
  }

  // e.g. 01 Jan 2025 [HH:MM:SS optional]
  m = str.match(/\b(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})/);
  if (m) {
    const [, d, monRaw, y] = m;
    const monMap: Record<string, string> = {
      jan: "01",
      feb: "02",
      mar: "03",
      apr: "04",
      may: "05",
      jun: "06",
      jul: "07",
      aug: "08",
      sep: "09",
      sept: "09",
      oct: "10",
      nov: "11",
      dec: "12",
    };
    const mo = monMap[monRaw.toLowerCase()] || null;
    if (mo) return `${y}-${mo}-${String(d).padStart(2, "0")}`;
  }

  // e.g. 2025 Jan 01 [HH:MM:SS optional]
  m = str.match(/\b(\d{4})\s+([A-Za-z]{3,})\s+(\d{1,2})/);
  if (m) {
    const [, y, monRaw, d] = m;
    const monMap: Record<string, string> = {
      jan: "01",
      feb: "02",
      mar: "03",
      apr: "04",
      may: "05",
      jun: "06",
      jul: "07",
      aug: "08",
      sep: "09",
      sept: "09",
      oct: "10",
      nov: "11",
      dec: "12",
    };
    const mo = monMap[monRaw.toLowerCase()] || null;
    if (mo) return `${y}-${mo}-${String(d).padStart(2, "0")}`;
  }

  // Fallback: let JS try
  const js = new Date(str);
  if (!Number.isNaN(js.getTime())) return js.toISOString().slice(0, 10);
  return null;
};

const applySearch = (rows: ParsedRow[], q: string) => {
  if (!q.trim()) return rows;
  const needles = q.toLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter((r) => {
    const bag = `${r.REMARKS || ""} ${r.REFERENCE || ""}`.toLowerCase();
    return needles.every((t) => bag.includes(t));
  });
};

const monthKey = (iso: string) => iso.slice(0, 7);
const twoMonthKey = (iso: string) => {
  const [y, m] = iso.split("-").map(Number);
  const start = m % 2 === 0 ? m - 1 : m; // [1-2], [3-4], ...
  const end = start + 1;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${y}-${pad(start)}..${y}-${pad(end)}`;
};
const quarterKey = (iso: string) => {
  const [y, m] = iso.split("-").map(Number);
  const q = Math.floor((m - 1) / 3) + 1;
  return `${y} Q${q}`;
};

const dateAddDays = (iso: string, days: number) => {
  const d = new Date(`${iso}T00:00:00`);
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
};

const startOfDataISO = (rows: ParsedRow[]): string | null => {
  const isos = rows.map((r) => toISO(r["TXN DATE"])).filter(Boolean) as string[];
  if (!isos.length) return null;
  isos.sort((a, b) => a.localeCompare(b));
  return isos[0];
};
const endOfDataISO = (rows: ParsedRow[]): string | null => {
  const isos = rows.map((r) => toISO(r["TXN DATE"])).filter(Boolean) as string[];
  if (!isos.length) return null;
  isos.sort((a, b) => a.localeCompare(b));
  return isos[isos.length - 1];
};

const sortRows = (rows: ParsedRow[], sortBy: SortKey) => {
  const withNums = rows.map((r) => ({
    ...r,
    _debit: parseMoney(r.DEBIT),
    _credit: parseMoney(r.CREDIT),
    _iso: toISO(r["TXN DATE"]),
  }));
  switch (sortBy) {
    case "largestCredit":
      return [...withNums].sort((a, b) => b._credit - a._credit);
    case "largestDebit":
      return [...withNums].sort((a, b) => b._debit - a._debit);
    case "txnDateAsc":
      return [...withNums].sort((a, b) => (a._iso || "").localeCompare(b._iso || ""));
    case "txnDateDesc":
      return [...withNums].sort((a, b) => (b._iso || "").localeCompare(a._iso || ""));
    default:
      return rows;
  }
};

// keep + use it for a visible breakdown
const classifyType = (
  remarks: string
): "transferIn" | "transferOut" | "pos" | "levy" | "airtime" | "data" | "other" => {
  const r = (remarks || "").toLowerCase();
  if (r.includes("electronic money transfer levy")) return "levy";
  if (r.startsWith("pos ") || r.includes("card payment-pos")) return "pos";
  if (r.includes("airtime")) return "airtime";
  if (r.includes("mobile data") || r.includes(" data")) return "data";
  if (r.startsWith("transfer from") || r.includes("received from")) return "transferIn";
  if (r.startsWith("transfer to") || r.startsWith("send to")) return "transferOut";
  return "other";
};

export const useAnalysisStore = create<AnalysisState>((set, get) => ({
  raw: [],
  filtered: [],
  totals: { debit: 0, credit: 0, net: 0, rows: 0, passRatio: 0 },
  buckets: [],
  typeSummary: {
    transferIn: { debit: 0, credit: 0, rows: 0 },
    transferOut: { debit: 0, credit: 0, rows: 0 },
    pos: { debit: 0, credit: 0, rows: 0 },
    levy: { debit: 0, credit: 0, rows: 0 },
    airtime: { debit: 0, credit: 0, rows: 0 },
    data: { debit: 0, credit: 0, rows: 0 },
    other: { debit: 0, credit: 0, rows: 0 },
  },

  // IMPORTANT: default to ALL so you always see data even if date parsing is quirky
  filters: {
    preset: "all",
    search: "",
    sortBy: "none",
    bucket: "monthly",
  },

  setRaw: (rows) => {
    set({ raw: rows });
    get().recompute();
  },

  setFilters: (patch) => {
    set((s) => ({ filters: { ...s.filters, ...patch } }));
    get().recompute();
  },

  recompute: () => {
    const { raw, filters } = get();

    if (!raw.length) {
      set({
        filtered: [],
        totals: { debit: 0, credit: 0, net: 0, rows: 0, passRatio: 0 },
        buckets: [],
        typeSummary: {
          transferIn: { debit: 0, credit: 0, rows: 0 },
          transferOut: { debit: 0, credit: 0, rows: 0 },
          pos: { debit: 0, credit: 0, rows: 0 },
          levy: { debit: 0, credit: 0, rows: 0 },
          airtime: { debit: 0, credit: 0, rows: 0 },
          data: { debit: 0, credit: 0, rows: 0 },
          other: { debit: 0, credit: 0, rows: 0 },
        },
      });
      return;
    }

    // Resolve range (robust)
    const maxISO = endOfDataISO(raw);
    const minISO = startOfDataISO(raw);
    let from: string | undefined;
    let to: string | undefined;

    const dateAdd = (n: number) => (maxISO ? dateAddDays(maxISO, n) : undefined);

    if (filters.preset === "last30") {
      to = maxISO || undefined;
      from = to ? dateAdd(-29) : undefined;
    } else if (filters.preset === "last60") {
      to = maxISO || undefined;
      from = to ? dateAdd(-59) : undefined;
    } else if (filters.preset === "last90") {
      to = maxISO || undefined;
      from = to ? dateAdd(-89) : undefined;
    } else if (filters.preset === "all") {
      from = minISO || undefined;
      to = maxISO || undefined;
    } else if (filters.preset === "custom") {
      from = filters.customFrom;
      to = filters.customTo;
    }

    // If we cannot parse any date at all → don't filter by date
    const anyISO = raw.some((r) => !!toISO(r["TXN DATE"]));
    const base = !anyISO
      ? raw
      : raw.filter((r) => {
          if (!from && !to) return true;
          const iso = toISO(r["TXN DATE"]);
          if (!iso) return false;
          if (from && iso < from) return false;
          if (to && iso > to) return false;
          return true;
        });

    const searched = applySearch(base, filters.search);
    const sorted = sortRows(searched, filters.sortBy);

    // Totals & pass %
    let debit = 0,
      credit = 0,
      pass = 0;
    for (const r of sorted) {
      debit += parseMoney(r.DEBIT);
      credit += parseMoney(r.CREDIT);
      if ((r.Check || "").toLowerCase() === "true") pass += 1;
    }
    const totals = {
      debit,
      credit,
      net: credit - debit,
      rows: sorted.length,
      passRatio: sorted.length ? pass / sorted.length : 0,
    };

    // Buckets
    const map = new Map<string, { debit: number; credit: number; rows: number }>();
    const keyer =
      filters.bucket === "monthly"
        ? monthKey
        : filters.bucket === "biMonthly"
        ? twoMonthKey
        : filters.bucket === "quarterly"
        ? quarterKey
        : () => "All";

    for (const r of sorted) {
      const iso = toISO(r["TXN DATE"]);
      const k = iso ? keyer(iso) : "All";
      const v = map.get(k) || { debit: 0, credit: 0, rows: 0 };
      v.debit += parseMoney(r.DEBIT);
      v.credit += parseMoney(r.CREDIT);
      v.rows += 1;
      map.set(k, v);
    }
    const buckets = Array.from(map.entries())
      .map(([label, v]) => ({
        label,
        debit: v.debit,
        credit: v.credit,
        net: v.credit - v.debit,
        rows: v.rows,
      }))
      .sort((a, b) => a.label.localeCompare(b.label));

    // Type summary (uses classifyType)
    const typeSummary: AnalysisState["typeSummary"] = {
      transferIn: { debit: 0, credit: 0, rows: 0 },
      transferOut: { debit: 0, credit: 0, rows: 0 },
      pos: { debit: 0, credit: 0, rows: 0 },
      levy: { debit: 0, credit: 0, rows: 0 },
      airtime: { debit: 0, credit: 0, rows: 0 },
      data: { debit: 0, credit: 0, rows: 0 },
      other: { debit: 0, credit: 0, rows: 0 },
    };
    for (const r of sorted) {
      const t = classifyType(r.REMARKS || "");
      typeSummary[t].debit += parseMoney(r.DEBIT);
      typeSummary[t].credit += parseMoney(r.CREDIT);
      typeSummary[t].rows += 1;
    }

    set({ filtered: sorted, totals, buckets, typeSummary });
  },
}));
