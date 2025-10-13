"use client";

import { ParsedRow } from "@/app/_types";
import React, { memo, useMemo } from "react";
import AutoSizer from "react-virtualized-auto-sizer";
import { List } from "react-window";
import type { RowComponentProps } from "react-window";

type RowPropsCtx = { rows: ParsedRow[] };

const ROW_HEIGHT = 44;
const gridColsHeader = "grid grid-cols-[120px_120px_130px_1fr_130px_120px_120px_70px_100px_15px]";
const gridCols = "grid grid-cols-[120px_120px_130px_1fr_130px_120px_120px_70px_100px]";
const tableBorders = "divide-x divide-gray-200";

const Cell = ({ children, className = "" }: { children: React.ReactNode; className?: string }) => (
  <div
    className={`px-3 py-2 truncate ${className}`}
    title={typeof children === "string" ? children : undefined}
  >
    {children}
  </div>
);

const RowComponent = memo(
  function RowComponent({ index, style, rows }: RowComponentProps<RowPropsCtx>) {
    const r = rows[index];
    const failed = r.Check === "FALSE";
    return (
      <div
        style={style}
        className={`${gridCols} border-b border-gray-100 ${tableBorders} ${
          failed
            ? "bg-red-100/70 hover:bg-red-100 border-white"
            : index % 2 === 0
            ? "bg-white hover:bg-blue-50/50"
            : "bg-gray-50 hover:bg-blue-50/50"
        } transition-colors`}
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
  const rowProps = useMemo<RowPropsCtx>(() => ({ rows }), [rows]);

  return (
    <div className="rounded-2xl border border-blue-100 overflow-hidden bg-white shadow-sm">
      {/* Header */}
      <div
        className={`sticky top-0 z-10 bg-blue-50 border-b border-gray-200 ${gridColsHeader} text-sm text-blue-900 ${tableBorders} font-semibold`}
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

      {/* Virtualized list */}
      <div style={{ height: "87dvh" }}>
        <AutoSizer style={{ height: "100%", width: "100%" }}>
          {({ height, width }) => (
            <List
              className="text-sm text-gray-800"
              rowComponent={RowComponent}
              rowCount={rows.length}
              rowHeight={ROW_HEIGHT}
              rowProps={rowProps}
              defaultHeight={height}
              style={{ height, width }}
            />
          )}
        </AutoSizer>
      </div>
    </div>
  );
}
