"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { FlameIcon, HashIcon, HomeIcon, InfoIcon, SearchIcon } from "./icons";

const MAIN = [
  { href: "/", label: "Home", Icon: HomeIcon, match: (p: string) => p === "/" || p.startsWith("/feed") || p.startsWith("/stories") },
  { href: "/problems", label: "Problems", Icon: FlameIcon, match: (p: string) => p.startsWith("/problems") },
  { href: "/search", label: "Search", Icon: SearchIcon, match: (p: string) => p.startsWith("/search") },
  { href: "/topics", label: "My topics", Icon: HashIcon, match: (p: string) => p.startsWith("/topics") },
  { href: "/how-it-works", label: "About", Icon: InfoIcon, match: (p: string) => p.startsWith("/how-it-works") },
];

const TOPICS = ["vllm", "kubernetes", "rust", "rag", "open weights", "gpu"];

const CATEGORIES = [
  { id: "bug_or_reliability", label: "Bugs" },
  { id: "cost_or_performance", label: "Cost & speed" },
  { id: "missing_capability", label: "Missing features" },
  { id: "workflow_friction", label: "Workflow pain" },
];

export function LeftNav() {
  const pathname = usePathname();
  const params = useSearchParams();
  const item = (active: boolean) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
      active ? "bg-signal-400/10 font-semibold text-signal-400" : "text-fg-200 hover:bg-field-850 hover:text-fg-50"
    }`;
  return (
    <nav className="sticky top-[88px] flex flex-col gap-6 text-sm" aria-label="Sections">
      <div className="flex flex-col gap-0.5">
        {MAIN.map(({ href, label, Icon, match }) => (
          <Link key={href} href={href} className={item(match(pathname))}>
            <Icon />
            {label}
          </Link>
        ))}
      </div>
      <div>
        <p className="px-3 text-xs font-semibold text-fg-500">Topics</p>
        <div className="mt-1 flex flex-col gap-0.5">
          {TOPICS.map((t) => (
            <Link
              key={t}
              href={`/search?q=${encodeURIComponent(t)}`}
              className={item(pathname === "/search" && params.get("q") === t)}
            >
              <HashIcon className="h-4 w-4 text-fg-500" />
              {t}
            </Link>
          ))}
        </div>
      </div>
      <div>
        <p className="px-3 text-xs font-semibold text-fg-500">Problems by type</p>
        <div className="mt-1 flex flex-col gap-0.5">
          {CATEGORIES.map((c) => (
            <Link
              key={c.id}
              href={`/problems?category=${c.id}`}
              className={item(pathname === "/problems" && params.get("category") === c.id)}
            >
              <span className="grid h-4 w-4 place-items-center">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
              </span>
              {c.label}
            </Link>
          ))}
        </div>
      </div>
    </nav>
  );
}
