// app/_components/LoadingSpinner.tsx
import React from "react";

type Props = {
  size?: number | string;
  baseColor?: string; // --payouto-fill
  pulseColor?: string; // --pulse-color
  speedSec?: number; // --pulse-speed (seconds)
  bg?: string; // optional background for the wrapper
};

export default function LoadingSpinner({
  size = 120,
  baseColor = "#ffffff",
  pulseColor = "#ffffff",
  speedSec = 2.2,
  bg = "#0b1a3b",
}: Props) {
  // expose CSS variables via style prop so you can override from parent too
  const vars = {
    "--payouto-fill": baseColor,
    "--pulse-color": pulseColor,
    "--pulse-speed": `${speedSec}s`,
  } as React.CSSProperties;

  return (
    <div className="flex items-center justify-center min-h-screen" style={{ background: bg }}>
      <svg
        viewBox="0 0 120 120"
        width={size}
        height={size}
        xmlns="http://www.w3.org/2000/svg"
        aria-label="Loading…"
        role="img"
        style={vars}
      >
        <style>{`
          /* allow external override */
          svg { color: var(--payouto-fill); }

          .spin {
            animation: spin var(--pulse-speed) linear infinite;
            transform-origin: 60px 60px;
          }
          @keyframes spin {
            to { transform: rotate(360deg); }
          }

          .pulse {
            stroke: var(--pulse-color);
            filter: url(#glow);
            animation: dash var(--pulse-speed) linear infinite;
          }
          @keyframes dash {
            to { stroke-dashoffset: -260; } /* ~ ring circumference */
          }
        `}</style>

        <defs>
          <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <mask id="payoutoMask">
            <rect width="120" height="120" fill="black" />
            {/* outer disk */}
            <circle cx="60" cy="60" r="56" fill="white" />
            {/* inner hole (ring) */}
            <circle cx="60" cy="60" r="28" fill="black" />
            {/* tail notch */}
            <path d="M34 24 L34 88 L20 98 L20 16 Z" fill="black" />
          </mask>
        </defs>

        {/* Base logo shape clipped by mask (uses currentColor) */}
        <rect width="120" height="120" fill="currentColor" mask="url(#payoutoMask)" />

        {/* Flowing pulse, also clipped by the logo mask */}
        <g mask="url(#payoutoMask)" className="spin">
          {/* r = (outerR + innerR) / 2 = (56 + 28) / 2 = 42; strokeWidth = 28 */}
          <circle
            className="pulse"
            cx="60"
            cy="60"
            r="42"
            fill="none"
            strokeWidth={28}
            strokeLinecap="round"
            strokeDasharray="40 220"
            strokeDashoffset={0}
          />
        </g>
      </svg>
    </div>
  );
}
