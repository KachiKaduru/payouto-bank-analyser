import { useParserStore } from "../_store/useParserStore";

import { Square } from "ldrs/react";
import "ldrs/react/Square.css";

export default function LoadingPage() {
  const loading = useParserStore((s) => s.loading);

  if (!loading) return null;

  return (
    <div className="w-full h-[100dvh] fixed top-0 left-0 bg-white/70 backdrop-blur-xs flex flex-col justify-center items-center gap-4 z-50">
      {/* // Default values shown */}
      <Square size="35" stroke="5" strokeLength="0.25" bgOpacity="0.1" speed="1.2" color="black" />
    </div>
  );
}
