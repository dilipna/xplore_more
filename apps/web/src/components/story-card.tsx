import Link from "next/link";
import type { RankSignals, StorySummary } from "@/lib/api";
import { isRecent, relativeTime } from "@/lib/format";
import { domainOf, initials, sourceColor, sourceName } from "@/lib/sources";
import { DocIcon, ExternalIcon, LayersIcon } from "./icons";

export function SourceAvatar({ id, name, size = 36 }: { id: string; name?: string; size?: number }) {
  const color = sourceColor(id);
  return (
    <span
      className="grid shrink-0 place-items-center rounded-full font-semibold"
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        color,
        background: `color-mix(in srgb, ${color} 14%, #000)`,
        boxShadow: `inset 0 0 0 1.5px color-mix(in srgb, ${color} 55%, transparent)`,
      }}
      aria-hidden="true"
    >
      {initials(name ?? sourceName(id))}
    </span>
  );
}

const THREE_HOURS = 3 * 3600 * 1000;

/** Rank change against the default weights: up, down, unchanged, or new to this list. */
function RankDelta({ delta }: { delta: number | "new" }) {
  if (delta === "new")
    return <span className="rounded bg-signal-400/10 px-1.5 py-0.5 font-mono text-[11px] text-signal-400">new</span>;
  if (delta === 0) return <span className="font-mono text-[11px] text-fg-600" aria-label="same rank">=</span>;
  const up = delta > 0;
  return (
    <span
      className={`font-mono text-[11px] ${up ? "text-signal-400" : "text-fg-500"}`}
      aria-label={`${up ? "up" : "down"} ${Math.abs(delta)} from the default ranking`}
    >
      {up ? "▲" : "▼"}
      {Math.abs(delta)}
    </span>
  );
}

function hoursLabel(h: number) {
  return h < 1 ? "<1 h old" : h < 48 ? `${Math.round(h)} h old` : `${Math.round(h / 24)} d old`;
}

/** Why the story ranks here: the heuristic's four parts for this story, straight from the API. */
function WhyRanked({ s }: { s: RankSignals }) {
  const parts = [
    { label: "coverage", value: s.coverage.toFixed(2) },
    { label: "authority", value: s.authority.toFixed(2) },
    { label: s.hn_points > 0 ? `community (${s.hn_points} pts)` : "community", value: s.community.toFixed(2) },
  ];
  return (
    <p className="relative mt-3 flex flex-wrap items-center gap-x-1.5 gap-y-1 font-mono text-[11px] text-fg-500">
      <span className="text-fg-400">Why here:</span>
      {parts.map((p, i) => (
        <span key={p.label}>
          {i > 0 && "+ "}
          {p.label} <span className="text-fg-200">{p.value}</span>
        </span>
      ))}
      <span>
        × freshness <span className="text-fg-200">{s.freshness.toFixed(2)}</span> ({hoursLabel(s.hours_since_published)})
      </span>
    </p>
  );
}

/** One story as a social-feed post: who published it, when, the headline, and what it merges. */
export function StoryCard({
  story,
  rank,
  lead = false,
  why = false,
  delta,
}: {
  story: StorySummary;
  rank?: number;
  lead?: boolean;
  /** Show the ranking explanation (feed pages). */
  why?: boolean;
  /** Rank change against the default weights, when the reader has tuned them. */
  delta?: number | "new";
}) {
  const src = story.sources[0] ?? "";
  const when = story.published_at ?? story.first_seen_at;
  const fresh = isRecent(when, THREE_HOURS);
  const others = story.sources.length - 1;
  return (
    <article className={`panel panel-hover group relative p-4 sm:p-5 ${lead ? "neon-edge" : ""}`}>
      <header className="flex items-center gap-3">
        <SourceAvatar id={src} />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="truncate text-sm font-semibold text-fg-50">
            {sourceName(src)}
            {others > 0 && <span className="font-normal text-fg-500"> and {others} more</span>}
          </p>
          <p className="mt-0.5 text-xs text-fg-500">
            {relativeTime(when)}
            {domainOf(story.url) && <> · {domainOf(story.url)}</>}
          </p>
        </div>
        {lead ? (
          <span className="rounded-full bg-signal-400 px-2.5 py-0.5 text-[11px] font-semibold text-black">Top story</span>
        ) : rank && delta !== undefined ? (
          <span className="flex items-center gap-1.5 font-mono text-xs text-fg-600">
            <RankDelta delta={delta} />#{rank}
          </span>
        ) : fresh ? (
          <span className="rounded-full border border-signal-400/40 bg-signal-400/10 px-2 py-0.5 text-[11px] font-semibold text-signal-400">
            New
          </span>
        ) : rank ? (
          <span className="font-mono text-xs text-fg-600">#{rank}</span>
        ) : null}
      </header>

      <h3
        className={`mt-3 text-pretty leading-snug font-semibold text-fg-50 [overflow-wrap:anywhere] group-hover:text-signal-300 ${
          lead ? "text-2xl md:text-[26px]" : "text-[17px]"
        }`}
      >
        <Link href={`/stories/${story.id}`} className="after:absolute after:inset-0">
          {story.title}
        </Link>
      </h3>

      {why && story.signals && <WhyRanked s={story.signals} />}

      <footer className="relative mt-4 flex flex-wrap items-center gap-1.5 text-xs text-fg-400">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
            story.source_count > 1 ? "bg-signal-400/10 text-signal-400" : "bg-field-800"
          }`}
        >
          <LayersIcon className="h-3.5 w-3.5" />
          {story.source_count === 1 ? "1 source" : `${story.source_count} sources`}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full bg-field-800 px-2.5 py-1">
          <DocIcon className="h-3.5 w-3.5" />
          {story.article_count === 1 ? "1 article" : `${story.article_count} articles`}
        </span>
        <a
          href={story.url}
          target="_blank"
          rel="noopener noreferrer"
          className="relative z-10 ml-auto inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 hover:bg-field-800 hover:text-signal-300"
        >
          Read original
          <ExternalIcon className="h-3.5 w-3.5" />
        </a>
      </footer>
    </article>
  );
}
