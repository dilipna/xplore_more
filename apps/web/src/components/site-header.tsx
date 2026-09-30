import Link from "next/link";
import { getStats } from "@/lib/api";
import { SearchIcon } from "./icons";
import { SinceTicker } from "./live";
import { PaletteButton } from "./command-palette";
import { NavLinks } from "./nav-links";

export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <svg width="26" height="26" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="10.5" fill="none" stroke="var(--color-signal-500)" strokeWidth="1.2" opacity="0.5" />
        <circle cx="12" cy="12" r="6" fill="none" stroke="var(--color-signal-400)" strokeWidth="1.2" opacity="0.8" />
        <circle cx="12" cy="12" r="2" fill="var(--color-signal-300)" />
        <line x1="12" y1="12" x2="20.5" y2="6.5" stroke="var(--color-signal-300)" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span className="text-lg font-bold tracking-tight text-fg-50">
        xplore<span className="text-signal-400">more</span>
      </span>
    </span>
  );
}

export async function SiteHeader() {
  const stats = await getStats();
  const live = stats.data?.last_indexed_at ?? null;
  return (
    <header className="sticky top-0 z-30 border-b hairline bg-field-950/90 backdrop-blur-md print:hidden">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-4 gap-y-2 px-4 py-2.5 sm:px-5 lg:h-15 lg:flex-nowrap">
        <Link href="/" aria-label="XploreMore home" className="shrink-0">
          <Wordmark />
        </Link>

        <form action="/search" method="get" role="search" className="relative mx-auto hidden w-full max-w-xl md:block">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 h-4 w-4 -translate-y-1/2 text-fg-500" />
          <input
            type="search"
            name="q"
            placeholder="Search stories, e.g. vllm, kubernetes, rust adoption"
            aria-label="Search stories"
            className="h-10 w-full rounded-full border hairline bg-field-900 pr-4 pl-10 text-sm text-fg-50 placeholder:text-fg-600 focus:border-signal-400 focus:bg-field-850 focus:outline-none"
          />
        </form>

        <div className="ml-auto md:ml-0">
          <PaletteButton />
        </div>
        <div className="flex shrink-0 items-center gap-2 rounded-full border hairline px-3 py-1.5 text-xs">
          {stats.data ? (
            <>
              <span className="live-dot" aria-hidden="true" />
              <span className="font-semibold text-signal-400">Live</span>
              <span className="hidden text-fg-500 sm:inline">
                <SinceTicker iso={live} prefix="· updated " />
              </span>
            </>
          ) : (
            <span className="text-amber-400">API unreachable</span>
          )}
        </div>

        {/* On screens without the left sidebar, the sections live here. */}
        <div className="w-full lg:hidden">
          <NavLinks />
        </div>
      </div>
    </header>
  );
}
