"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Shows a short "N new stories" toast when the silent auto-refresh brings in stories that
 * weren't on the page before. Compares real story ids between renders; says nothing otherwise.
 */
export function FeedPulse({ ids }: { ids: number[] }) {
  const seen = useRef<Set<number> | null>(null);
  const [fresh, setFresh] = useState(0);
  const key = ids.join(",");

  useEffect(() => {
    const current = key ? key.split(",").map(Number) : [];
    if (seen.current === null) {
      seen.current = new Set(current);
      return;
    }
    const added = current.filter((id) => !seen.current!.has(id)).length;
    current.forEach((id) => seen.current!.add(id));
    if (added === 0) return;
    const show = setTimeout(() => setFresh(added), 0);
    const hide = setTimeout(() => setFresh(0), 5000);
    return () => {
      clearTimeout(show);
      clearTimeout(hide);
    };
  }, [key]);

  if (!fresh) return null;
  return (
    <div className="pointer-events-none fixed inset-x-0 top-20 z-40 flex justify-center" role="status">
      <span className="rounded-full bg-signal-400 px-4 py-1.5 text-sm font-semibold text-black shadow-[0_0_24px_-4px_rgb(57_255_127/0.8)]">
        {fresh === 1 ? "1 new story" : `${fresh} new stories`}
      </span>
    </div>
  );
}
