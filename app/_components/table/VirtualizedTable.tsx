"use client";

import { ParsedRow } from "@/app/_types";
import React, { memo, useMemo } from "react";
import AutoSizer from "react-virtualized-auto-sizer";
import { List } from "react-window";
import type { RowComponentProps } from "react-window";

type RowPropsCtx = { rows: ParsedRow[] };

const ROW_HEIGHT = 44;
const gridCols = "grid grid-cols-[120px_120px_130px_1fr_130px_120px_120px_70px_100px]";
const tableBorders = "divide-x divide-gray-500";

const Cell = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div
    className={`p-3 truncate ${className}`}
    title={typeof children === "string" ? children : undefined}
  >
    {children}
  </div>
);

// Row component (v2 API passes rowProps directly into the row)
const RowComponent = memo(
  function RowComponent({ index, style, rows }: RowComponentProps<RowPropsCtx>) {
    const r = rows[index];
    return (
      <div
        style={style}
        className={`${gridCols} border-b border-gray-500 ${tableBorders} hover:bg-gray-50 ${
          r.Check === "FALSE"
            ? "bg-red-100 hover:bg-red-100"
            : index % 2 === 0
            ? "bg-white"
            : "bg-gray-100"
        }`}
      >
        <Cell>{r.TXN_DATE}</Cell>
        <Cell>{r.VAL_DATE}</Cell>
        <Cell>{r.REFERENCE}</Cell>
        <Cell className="max-w-[900px]">{r.REMARKS}</Cell>
        <Cell className="text-right">{r.DEBIT}</Cell>
        <Cell className="text-right">{r.CREDIT}</Cell>
        <Cell className="text-right">{r.BALANCE}</Cell>
        <Cell>{r.Check}</Cell>
        <Cell>{r["Check 2"]}</Cell>
      </div>
    );
  },
  (prev, next) => prev.index === next.index && prev.rows === next.rows
);

export default function VirtualizedTable({ rows }: { rows: ParsedRow[] }) {
  // keep a stable reference to avoid re-rendering all rows
  const rowProps = useMemo<RowPropsCtx>(() => ({ rows }), [rows]);

  return (
    <div className="rounded-2xl border overflow-hidden bg-white no-scrollbar">
      {/* Header */}
      <div
        className={`sticky top-0 z-10 bg-gray-300 border-b ${gridCols} text-sm text-gray-900 ${tableBorders} font-semibold`}
      >
        <Cell>TXN DATE</Cell>
        <Cell>VAL DATE</Cell>
        <Cell>REFERENCE</Cell>
        <Cell>REMARKS</Cell>
        <Cell className="text-right">DEBIT</Cell>
        <Cell className="text-right">CREDIT</Cell>
        <Cell className="text-right">BALANCE</Cell>
        <Cell>Check</Cell>
        <Cell>Check 2</Cell>
      </div>

      {/* Body — List uses ResizeObserver; give it a container height */}
      <div style={{ height: "70dvh" }}>
        <AutoSizer style={{ width: "100%", height: "100%" }}>
          {({ height, width }) => (
            <List
              className="text-sm"
              rowComponent={RowComponent}
              rowCount={rows.length}
              rowHeight={ROW_HEIGHT}
              rowProps={rowProps}
              // optional for SSR/hydration to avoid a flash:
              defaultHeight={height}
              style={{ height, width }}
            />
          )}
        </AutoSizer>
      </div>
    </div>
  );
}
