import Link from "next/link";
import { getStats } from "@/lib/api";
import { SinceTicker } from "./live";
import { NavLinks } from "./nav-links";

export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="10.5" fill="none" stroke="var(--color-signal-500)" strokeWidth="1.2" opacity="0.5" />
        <circle cx="12" cy="12" r="6" fill="none" stroke="var(--color-signal-400)" strokeWidth="1.2" opacity="0.8" />
        <circle cx="12" cy="12" r="2" fill="var(--color-signal-300)" />
        <line x1="12" y1="12" x2="20.5" y2="6.5" stroke="var(--color-signal-300)" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span className="text-[17px] font-semibold tracking-tight text-fg-50">
        Xplore<span className="text-signal-400">More</span>
      </span>
    </span>
  );
}

export async function SiteHeader() {
  const stats = await getStats();
  const live = stats.data?.last_indexed_at ?? null;
  return (
    <header className="sticky top-0 z-30 border-b hairline bg-field-950/85 backdrop-blur-md">
      {/* Below md the nav wraps to its own full-width row; the links don't fit beside the wordmark at 390 px. */}
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-5 py-3 md:h-15 md:flex-nowrap">
        <Link href="/" aria-label="XploreMore home" className="shrink-0">
          <Wordmark />
        </Link>
        <NavLinks />
        <form action="/search" method="get" className="ml-auto hidden lg:block" role="search">
          <input
            type="search"
            name="q"
            placeholder="Search news"
            aria-label="Search news"
            className="h-9 w-56 rounded-lg border hairline bg-field-900 px-3 text-sm text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:outline-none"
          />
        </form>
        <div className="ml-auto hidden items-center gap-2 text-xs text-fg-400 md:flex lg:ml-0">
          {stats.data ? (
            <>
              <span className="live-dot" aria-hidden="true" />
              <span className="text-signal-400">Live</span>
              <span className="text-fg-500">
                <SinceTicker iso={live} prefix="· updated " />
              </span>
            </>
          ) : (
            <span className="text-amber-400">API unreachable</span>
          )}
        </div>
      </div>
    </header>
  );
}
