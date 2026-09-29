"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/** Re-render every `intervalMs` after mount. Time-based text renders only on the client, so the
 *  server HTML and the first client render always agree (no hydration mismatch). */
function useNow(intervalMs = 1000): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    const tick = () => setNow(new Date());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, intervalMs);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, [intervalMs]);
  return now;
}

/** "updated 4m ago", kept current from a real timestamp. */
export function SinceTicker({ iso, prefix = "" }: { iso: string | null; prefix?: string }) {
  const now = useNow(15_000);
  if (!iso) return <span>{prefix}—</span>;
  if (!now) return <span>{prefix}…</span>;
  const m = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 60_000));
  const text = m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 48 * 60 ? `${Math.floor(m / 60)}h ago` : `${Math.floor(m / 1440)}d ago`;
  return <span className="tabular-nums">{prefix + text}</span>;
}

/** Quietly re-fetches the server-rendered page every `seconds` while the tab is visible. */
export function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState === "visible") router.refresh();
    }, seconds * 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return null;
}
