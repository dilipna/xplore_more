"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { MapResponse } from "@/lib/api";
import { SignalMap } from "./signal-map";

/** The home page's live radar. Loaded after the page renders, so the feed never waits for the layout. */
export function MapHero() {
  const [data, setData] = useState<MapResponse | null | "error">(null);
  useEffect(() => {
    const ctl = new AbortController();
    fetch("/api/map", { signal: ctl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => !ctl.signal.aborted && setData("error"));
    return () => ctl.abort();
  }, []);

  return (
    <div className="relative h-64 sm:h-72">
      {data && data !== "error" ? (
        <SignalMap points={data.points} islands={data.islands} mode="hero" className="h-full w-full" />
      ) : (
        <div className="absolute inset-0 grid place-items-center" aria-busy={data === null}>
          <div className="radar-idle" aria-hidden="true" />
          <p className="absolute bottom-3 font-mono text-[11px] text-fg-600">
            {data === "error" ? "The map is unavailable right now." : "Laying out this week by meaning…"}
          </p>
        </div>
      )}
      <Link
        href="/map"
        className="absolute right-3 bottom-3 rounded-full bg-signal-400 px-3.5 py-1.5 text-xs font-bold text-black shadow-[0_0_24px_rgb(57_255_127/0.5)] hover:bg-signal-300"
      >
        Explore the map →
      </Link>
    </div>
  );
}
