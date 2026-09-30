"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { StorySummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";
import { sourceName } from "@/lib/sources";
import { SearchIcon } from "./icons";

const PAGES = [
  { label: "Home", href: "/", hint: "Top stories" },
  { label: "Signal map", href: "/map", hint: "The week, laid out by meaning" },
  { label: "All stories", href: "/feed", hint: "Tune the ranking" },
  { label: "Problems", href: "/problems", hint: "What engineers keep reporting" },
  { label: "Daily briefing", href: "/briefing", hint: "Top 5 and top 3, print-ready" },
  { label: "My topics", href: "/topics", hint: "Followed searches" },
  { label: "About", href: "/how-it-works", hint: "How it works and the evaluations" },
];

type Row = { key: string; label: string; hint: string; href: string; kind: "page" | "story" | "search" };

/** ⌘K / Ctrl+K: jump anywhere, or search stories as you type (hybrid search through a same-origin proxy). */
export function CommandPalette() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [stories, setStories] = useState<StorySummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    setQ("");
    setStories([]);
    setActive(0);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") close();
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("xm:palette", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("xm:palette", onOpen);
    };
  }, [close]);

  useEffect(() => {
    const term = q.trim();
    if (!open || term.length < 2) return;
    const ctl = new AbortController();
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await fetch(`/api/search?q=${encodeURIComponent(term)}`, { signal: ctl.signal });
        const body = await r.json();
        setStories(body.results ?? []);
        setActive(0);
      } catch {
        // aborted or offline: keep the previous results
      } finally {
        setLoading(false);
      }
    }, 140);
    return () => {
      clearTimeout(timer);
      ctl.abort();
    };
  }, [q, open]);

  if (!open) return null;
  const term = q.trim().toLowerCase();
  const rows: Row[] = [
    ...PAGES.filter((p) => !term || p.label.toLowerCase().includes(term)).map((p) => ({
      key: p.href,
      label: p.label,
      hint: p.hint,
      href: p.href,
      kind: "page" as const,
    })),
    ...(term.length >= 2 ? stories : []).map((s) => ({
      key: `s${s.id}`,
      label: s.title,
      hint: `${sourceName(s.sources[0] ?? "")} · ${relativeTime(s.published_at ?? s.first_seen_at)}`,
      href: `/stories/${s.id}`,
      kind: "story" as const,
    })),
    ...(term.length >= 2
      ? [{ key: "all", label: `Search all stories for “${q.trim()}”`, hint: "Full results page", href: `/search?q=${encodeURIComponent(q.trim())}`, kind: "search" as const }]
      : []),
  ];
  const go = (row: Row | undefined) => {
    if (!row) return;
    close();
    router.push(row.href);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/70 px-4 pt-[12vh] backdrop-blur-sm print:hidden" onMouseDown={close}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        onMouseDown={(e) => e.stopPropagation()}
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-signal-400/30 bg-field-900 shadow-[0_0_60px_rgb(57_255_127/0.15)]"
      >
        <div className="flex items-center gap-3 border-b hairline px-4">
          <SearchIcon className="h-4 w-4 text-signal-400" />
          <input
            ref={input}
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive((a) => Math.min(rows.length - 1, a + 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive((a) => Math.max(0, a - 1));
              } else if (e.key === "Enter") {
                e.preventDefault();
                go(rows[active]);
              }
            }}
            placeholder="Search stories or jump to a page…"
            aria-label="Search stories or jump to a page"
            className="h-14 flex-1 bg-transparent text-[15px] text-fg-50 placeholder:text-fg-600 focus:outline-none"
          />
          {loading && <span className="font-mono text-[10px] text-signal-400">searching…</span>}
        </div>
        <ul className="max-h-[55vh] overflow-y-auto p-2" role="listbox" aria-label="Results">
          {rows.map((row, i) => (
            <li key={row.key} role="option" aria-selected={i === active}>
              <button
                type="button"
                onMouseEnter={() => setActive(i)}
                onClick={() => go(row)}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left ${i === active ? "bg-signal-400/10" : ""}`}
              >
                <span
                  className={`shrink-0 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase ${
                    row.kind === "story" ? "bg-signal-400/15 text-signal-400" : row.kind === "search" ? "bg-sky-400/15 text-sky-300" : "bg-field-800 text-fg-400"
                  }`}
                >
                  {row.kind === "page" ? "go" : row.kind}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg-50">{row.label}</span>
                  <span className="block truncate text-xs text-fg-500">{row.hint}</span>
                </span>
              </button>
            </li>
          ))}
          {term.length >= 2 && !loading && stories.length === 0 && (
            <li className="px-3 py-2 text-xs text-fg-500">No stories match yet. Keep typing, or press Enter to search.</li>
          )}
        </ul>
        <div className="flex justify-between border-t hairline px-4 py-2 font-mono text-[10px] text-fg-600">
          <span>↑↓ move · ↵ open · esc close</span>
          <span>hybrid search, no LLM</span>
        </div>
      </div>
    </div>
  );
}

/** Header button that opens the palette (for mouse and touch users). */
export function PaletteButton() {
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new Event("xm:palette"))}
      className="inline-flex h-9 shrink-0 items-center gap-2 rounded-full border hairline bg-field-900 px-3 text-xs text-fg-400 hover:border-signal-400/60 hover:text-fg-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-400"
      aria-label="Open the command palette"
    >
      <SearchIcon className="h-3.5 w-3.5" />
      <span className="hidden sm:inline">Jump to</span>
      <kbd className="rounded border border-field-600 px-1 font-mono text-[10px] text-fg-500">⌘K</kbd>
    </button>
  );
}
