import Link from "next/link";
import type { StorySummary } from "@/lib/api";
import { relativeTime } from "@/lib/format";

function coverage(s: StorySummary) {
  return s.source_count > 1 ? `${s.source_count} sources → 1 story` : "1 source";
}

/** The feed's #1 story as a lead card, the next ones as a ranked list. Real ranked data only. */
export function TopStories({ stories, windowLabel }: { stories: StorySummary[]; windowLabel: string }) {
  const [lead, ...rest] = stories;
  if (!lead) return null;
  return (
    <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
      <article className="panel neon-edge sweep relative flex min-w-0 flex-col justify-between overflow-hidden p-6 md:p-8">
        {/* Outlined rank numeral: fills the card without inventing content. */}
        <span
          aria-hidden="true"
          className="pointer-events-none absolute -right-4 -bottom-10 font-mono text-[200px] leading-none font-bold text-transparent select-none md:text-[260px]"
          style={{ WebkitTextStroke: "1.5px rgb(57 255 127 / 0.16)" }}
        >
          01
        </span>
        <div className="relative">
          <div className="flex flex-wrap items-center gap-3 font-mono text-[11px]">
            <span className="rounded-md bg-signal-400 px-2 py-0.5 font-semibold tracking-[0.15em] text-black">#1 NOW</span>
            <span className="text-fg-500">top story · last {windowLabel}</span>
          </div>
          <h3 className="mt-5 text-pretty text-2xl leading-tight font-semibold tracking-tight text-fg-50 [overflow-wrap:anywhere] md:text-[32px]">
            <Link href={`/stories/${lead.id}`} className="transition-colors after:absolute after:inset-0 hover:text-signal-300">
              {lead.title}
            </Link>
          </h3>
        </div>
        <div className="relative mt-8">
          <p className="max-w-md text-sm leading-relaxed text-fg-400">
            Ranked first by coverage across sources, source authority and Hacker News engagement, decayed by
            freshness (18-hour half-life). Every outlet covering it is folded into this one story.
          </p>
          <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-xs">
            <span className={lead.source_count > 1 ? "neon-text" : "text-fg-400"}>{coverage(lead)}</span>
            <span className="truncate text-fg-500">{lead.sources.slice(0, 4).join(" · ")}</span>
            <span className="text-fg-500">{relativeTime(lead.published_at ?? lead.first_seen_at)}</span>
            <span className="text-signal-400">read the story →</span>
          </div>
        </div>
      </article>

      <ol className="panel flex min-w-0 flex-col divide-y divide-signal-400/10 overflow-hidden">
        {rest.slice(0, 5).map((s, i) => (
          <li key={s.id} className="group relative flex gap-4 px-5 py-4 transition-colors hover:bg-field-850">
            <span className="w-6 shrink-0 pt-0.5 font-mono text-sm text-signal-500 tabular-nums group-hover:neon-text">
              {String(i + 2).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <Link
                href={`/stories/${s.id}`}
                className="line-clamp-2 text-[15px] leading-snug text-fg-50 [overflow-wrap:anywhere] after:absolute after:inset-0 group-hover:text-signal-300"
              >
                {s.title}
              </Link>
              <p className="mt-1 flex gap-3 font-mono text-[11px] text-fg-500">
                <span className={`truncate ${s.source_count > 1 ? "text-signal-300" : ""}`}>{coverage(s)}</span>
                <span className="shrink-0">{relativeTime(s.published_at ?? s.first_seen_at)}</span>
              </p>
            </div>
          </li>
        ))}
        <li className="px-5 py-3">
          <Link href="/feed" className="font-mono text-xs text-signal-400 hover:text-signal-300">
            full ranked feed →
          </Link>
        </li>
      </ol>
    </div>
  );
}
