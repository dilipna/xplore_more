"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

/** Re-render once a second after mount. Time-based text renders only on the client, so the
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

/** Current UTC time, ticking. */
export function LiveClock() {
  const now = useNow();
  return (
    <span className="tabular-nums" suppressHydrationWarning>
      {now ? `${now.toISOString().slice(11, 19)} UTC` : "--:--:-- UTC"}
    </span>
  );
}

/** "indexed 4m 12s ago", counting up live from a real timestamp. */
export function SinceTicker({ iso, prefix = "" }: { iso: string | null; prefix?: string }) {
  const now = useNow();
  if (!iso) return <span>{prefix}—</span>;
  if (!now) return <span>{prefix}…</span>;
  const s = Math.max(0, Math.floor((now.getTime() - new Date(iso).getTime()) / 1000));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  const text = d > 0 ? `${d}d ${h}h ago` : h > 0 ? `${h}h ${m}m ago` : `${m}m ${String(s % 60).padStart(2, "0")}s ago`;
  return <span className="tabular-nums">{prefix + text}</span>;
}

/** Re-fetches the server-rendered page every `seconds` while the tab is visible, with a countdown. */
export function AutoRefresh({ seconds = 60 }: { seconds?: number }) {
  const router = useRouter();
  const [left, setLeft] = useState(seconds);
  const leftRef = useRef(seconds);
  useEffect(() => {
    const id = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      leftRef.current -= 1;
      if (leftRef.current <= 0) {
        leftRef.current = seconds;
        router.refresh();
      }
      setLeft(leftRef.current);
    }, 1000);
    return () => clearInterval(id);
  }, [router, seconds]);
  return (
    <span className="inline-flex items-center gap-2 tabular-nums" title="This page re-fetches live data automatically">
      <span className="relative h-1 w-10 overflow-hidden rounded-full bg-field-700" aria-hidden="true">
        <span
          className="absolute inset-y-0 left-0 rounded-full bg-signal-400 transition-[width] duration-1000 ease-linear"
          style={{ width: `${(left / seconds) * 100}%` }}
        />
      </span>
      refresh {left}s
    </span>
  );
}

/** Counts up to a real value once on mount (ease-out). The server renders the final value. */
export function CountUp({ value, durationMs = 1400 }: { value: number; durationMs?: number }) {
  const [shown, setShown] = useState(value);
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches || value <= 0) return;
    let raf = 0;
    const start = performance.now();
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / durationMs);
      setShown(Math.round(value * (1 - Math.pow(1 - p, 3))));
      if (p < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value, durationMs]);
  return <span className="tabular-nums">{shown.toLocaleString("en-US")}</span>;
}
