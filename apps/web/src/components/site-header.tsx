import Link from "next/link";
import { getStats } from "@/lib/api";
import { LiveClock, SinceTicker } from "./live";
import { NavLinks } from "./nav-links";

export function Wordmark() {
  return (
    <span className="flex items-center gap-2.5">
      <svg
        width="24"
        height="24"
        viewBox="0 0 24 24"
        aria-hidden="true"
        style={{ filter: "drop-shadow(0 0 5px rgb(57 255 127 / 0.7))" }}
      >
        <circle cx="12" cy="12" r="10.5" fill="none" stroke="var(--color-signal-500)" strokeWidth="1.2" opacity="0.5" />
        <circle cx="12" cy="12" r="6" fill="none" stroke="var(--color-signal-400)" strokeWidth="1.2" opacity="0.8" />
        <circle cx="12" cy="12" r="2" fill="var(--color-signal-300)" />
        <line x1="12" y1="12" x2="20.5" y2="6.5" stroke="var(--color-signal-300)" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
      <span className="text-[17px] font-semibold tracking-tight text-fg-50">
        Xplore<span className="neon-text">More</span>
      </span>
    </span>
  );
}

export async function SiteHeader() {
  const stats = await getStats();
  const live = stats.data?.last_indexed_at ?? null;
  return (
    <header className="sticky top-0 z-30 border-b hairline bg-field-950/80 backdrop-blur-md">
      {/* Below md the nav wraps to its own full-width row; four links don't fit beside the wordmark at 390 px. */}
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-5 py-3 md:h-15 md:flex-nowrap">
        <Link href="/" aria-label="XploreMore home">
          <Wordmark />
        </Link>
        <NavLinks />
        <div className="hidden items-center gap-3 font-mono text-[11px] text-fg-400 md:flex">
          {stats.data ? (
            <>
              <span className="flex items-center gap-1.5 rounded-md border border-signal-400/40 bg-signal-400/10 px-2 py-0.5 font-semibold tracking-[0.15em] text-signal-400">
                <span className="live-dot" aria-hidden="true" />
                LIVE
              </span>
              <span className="flex flex-col leading-tight">
                <LiveClock />
                <SinceTicker iso={live} prefix="indexed " />
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
