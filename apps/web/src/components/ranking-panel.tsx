"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { DEFAULT_WEIGHTS, KNOBS, type Weights, weightParams } from "@/lib/ranking";

/**
 * Sliders for the feed heuristic. Moving one updates the URL (so a tuned feed is shareable) and
 * the server re-ranks with those weights; the API key never reaches the browser.
 */
export function RankingPanel({ weights }: { weights: Weights }) {
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const [draft, setDraft] = useState<Weights>(weights);
  const [pending, startTransition] = useTransition();
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isDefault = KNOBS.every((k) => draft[k.key] === DEFAULT_WEIGHTS[k.key]);

  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);

  function navigate(next: Weights) {
    const params = new URLSearchParams();
    const window = search.get("window");
    if (window) params.set("window", window);
    for (const [k, v] of Object.entries(weightParams(next))) params.set(k, v);
    const qs = params.toString();
    startTransition(() => router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false }));
  }

  function change(next: Weights) {
    setDraft(next);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => navigate(next), 250);
  }

  return (
    <section className="panel mb-4 p-4 sm:p-5" aria-labelledby="ranking-title">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 id="ranking-title" className="text-base font-semibold text-fg-50">
          Ranking
        </h2>
        <p className="text-xs text-fg-500">
          score = (coverage + authority + community) × freshness. Move a slider to re-rank.
        </p>
        <span className="ml-auto text-xs text-fg-500" aria-live="polite">
          {pending ? "Re-ranking…" : isDefault ? "Default weights" : "Custom weights"}
        </span>
      </div>
      <div className="mt-4 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        {KNOBS.map((k) => (
          <label key={k.key} className="block">
            <span className="flex items-baseline justify-between gap-2 text-sm">
              <span className="font-medium text-fg-200">{k.label}</span>
              <span className="font-mono text-xs text-signal-400">
                {k.key === "half_life_hours" ? `${draft[k.key]} h` : draft[k.key].toFixed(2)}
              </span>
            </span>
            <input
              type="range"
              min={k.min}
              max={k.max}
              step={k.step}
              value={draft[k.key]}
              onChange={(e) => change({ ...draft, [k.key]: Number(e.target.value) })}
              className="mt-2 w-full accent-[var(--color-signal-400)] disabled:opacity-50"
              aria-describedby={`help-${k.key}`}
            />
            <span id={`help-${k.key}`} className="mt-1 block text-xs text-fg-500">
              {k.help}
            </span>
          </label>
        ))}
      </div>
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={() => change({ ...DEFAULT_WEIGHTS })}
          disabled={isDefault}
          className="rounded-full border border-field-600 px-3.5 py-1.5 text-sm font-semibold text-fg-200 hover:border-signal-400 hover:text-signal-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-400 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-field-600 disabled:hover:text-fg-200"
        >
          Reset to default
        </button>
      </div>
    </section>
  );
}
