"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

const KEYS: [string, string][] = [
  ["/", "Search"],
  ["j / k", "Next / previous story or problem"],
  ["o or Enter", "Open the selected one"],
  ["g then h", "Home"],
  ["?", "Show or hide this help"],
];

function typing(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
}

/** Keyboard shortcuts for readers who live on the keyboard. Cards are the page's <article> elements. */
export function KeyboardShortcuts() {
  const router = useRouter();
  const [help, setHelp] = useState(false);
  const index = useRef(-1);
  const pendingG = useRef(false);

  useEffect(() => {
    const cards = () => [...document.querySelectorAll<HTMLElement>("main article")];
    const select = (i: number) => {
      const list = cards();
      if (list.length === 0) return;
      list.forEach((c) => c.removeAttribute("data-kb-selected"));
      index.current = Math.max(0, Math.min(list.length - 1, i));
      const card = list[index.current];
      card.setAttribute("data-kb-selected", "");
      card.scrollIntoView({ block: "nearest", behavior: "smooth" });
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      if (pendingG.current) {
        pendingG.current = false;
        if (e.key === "h") return router.push("/");
      }
      switch (e.key) {
        case "/": {
          const input = document.querySelector<HTMLInputElement>('input[name="q"]');
          if (input) {
            e.preventDefault();
            input.focus();
          } else router.push("/search");
          break;
        }
        case "j":
          select(index.current + 1);
          break;
        case "k":
          select(index.current - 1);
          break;
        case "o":
        case "Enter": {
          // Enter on a focused link or button keeps its normal meaning.
          if (e.key === "Enter" && document.activeElement && document.activeElement !== document.body) break;
          const card = cards()[index.current];
          const link = card?.querySelector<HTMLAnchorElement>("h2 a, h3 a, a[href^='/']");
          if (link) {
            e.preventDefault();
            link.click();
          }
          break;
        }
        case "g":
          pendingG.current = true;
          break;
        case "?":
          setHelp((h) => !h);
          break;
        case "Escape":
          setHelp(false);
          break;
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  if (!help) return null;
  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby="kb-title"
      className="fixed right-4 bottom-4 z-50 w-80 rounded-xl border hairline bg-field-900 p-5 shadow-2xl print:hidden"
    >
      <div className="flex items-baseline justify-between">
        <h2 id="kb-title" className="text-sm font-semibold text-fg-50">
          Keyboard shortcuts
        </h2>
        <button
          type="button"
          onClick={() => setHelp(false)}
          className="text-xs text-fg-500 hover:text-signal-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-400"
        >
          Close
        </button>
      </div>
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        {KEYS.map(([k, what]) => (
          <div key={k} className="contents">
            <dt>
              <kbd className="rounded border border-field-600 bg-field-850 px-1.5 py-0.5 font-mono text-xs text-signal-300">{k}</kbd>
            </dt>
            <dd className="text-fg-400">{what}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
