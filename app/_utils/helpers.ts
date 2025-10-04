import { ParsedRow } from "../_types";

export const toISO = (s: string): string | null => {
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

export const parseMoney = (s: string | number | null | undefined): number => {
  if (!s) return 0;

  if (typeof s === "number") return s;
  const clean = s.replace(/[₦,\s]/g, "");
  const n = Number(clean);
  return Number.isFinite(n) ? n : 0;
};

export const applySearch = (rows: ParsedRow[], q: string) => {
  if (!q.trim()) return rows;
  const needles = q.toLowerCase().split(/\s+/).filter(Boolean);
  return rows.filter((r) => {
    const bag = `${r.REMARKS || ""} ${r.REFERENCE || ""}`.toLowerCase();
    return needles.every((t) => bag.includes(t));
  });
};

export function formatNaira(amount: number | string): string {
  const num = Number(parseMoney(amount));

  if (isNaN(num)) return "₦0.00";

  return num.toLocaleString("en-NG", {
    style: "currency",
    currency: "NGN",
    minimumFractionDigits: 2,
  });
}

export function formatMonthYear(period: string): string {
  if (!period) return "";

  const cleaned = period.trim();

  // Handle "All" (case-insensitive)
  if (/^all$/i.test(cleaned)) return "All Periods";

  // Handle range like "2025-05..2025-06"
  if (cleaned.includes("..")) {
    const [start, end] = cleaned.split("..").map((p) => p.trim());
    const startDate = new Date(start.length === 7 ? `${start}-01` : start);
    const endDate = new Date(end.length === 7 ? `${end}-01` : end);
    if (!isNaN(startDate.getTime()) && !isNaN(endDate.getTime())) {
      const startText = startDate.toLocaleDateString("en-NG", {
        year: "numeric",
        month: "short",
      });
      const endText = endDate.toLocaleDateString("en-NG", {
        year: "numeric",
        month: "short",
      });
      return `${startText} – ${endText}`;
    }
  }

  // Handle quarters like "2025 Q2"
  const quarterMatch = cleaned.match(/^(\d{4})\s*[Qq](\d)$/);
  if (quarterMatch) {
    const [, year, q] = quarterMatch;
    const quarterNames = {
      1: "Q1 (Jan–Mar)",
      2: "Q2 (Apr–Jun)",
      3: "Q3 (Jul–Sep)",
      4: "Q4 (Oct–Dec)",
    } as const;
    return `${year} ${quarterNames[Number(q) as keyof typeof quarterNames]}`;
  }

  // Handle single month or date like "2025-05"
  const single = new Date(cleaned.length === 7 ? `${cleaned}-01` : cleaned);
  if (!isNaN(single.getTime())) {
    return single.toLocaleDateString("en-NG", {
      year: "numeric",
      month: "long",
    });
  }

  // Fallback: return as-is
  return cleaned;
}
