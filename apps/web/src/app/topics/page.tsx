import type { Metadata } from "next";
import Link from "next/link";
import { NewSinceVisit, TopicsLoader, UnfollowLink } from "@/components/follow";
import { RightRail } from "@/components/right-rail";
import { Shell } from "@/components/shell";
import { StoryCard } from "@/components/story-card";
import { Unavailable } from "@/components/ui";
import { search } from "@/lib/api";
import { MAX_FOLLOWS, normalizeTopic } from "@/lib/follows";

export const dynamic = "force-dynamic";
export const metadata: Metadata = { title: "My topics" };

const PER_TOPIC = 4;

export default async function TopicsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { t } = await searchParams;
  const topics = [...new Set((Array.isArray(t) ? t : t ? [t] : []).map(normalizeTopic).filter(Boolean))].slice(
    0,
    MAX_FOLLOWS,
  );
  const results = await Promise.all(topics.map((q) => search(q, PER_TOPIC)));

  return (
    <Shell rail={<RightRail />}>
      <section className="panel mb-4 p-5">
        <h1 className="text-2xl font-bold tracking-tight">My topics</h1>
        <p className="mt-1.5 text-sm leading-relaxed text-fg-400">
          The top stories for each topic you follow. Follows are saved in this browser only: there is no account, and the
          server doesn&apos;t keep them.
        </p>
      </section>
      <TopicsLoader current={topics} />
      <div className="flex flex-col gap-8">
        {topics.map((q, i) => {
          const r = results[i];
          return (
            <section key={q} aria-labelledby={`topic-${i}`}>
              <div className="mb-3 flex items-baseline gap-3">
                <h2 id={`topic-${i}`} className="text-lg font-semibold text-fg-50">
                  <Link href={`/search?q=${encodeURIComponent(q)}`} className="hover:text-signal-300">
                    {q}
                  </Link>
                </h2>
                <UnfollowLink topic={q} />
              </div>
              {!r.data ? (
                <Unavailable what={`stories about ${q}`} />
              ) : r.data.results.length === 0 ? (
                <p className="text-sm text-fg-400">No stories match this topic yet.</p>
              ) : (
                <div className="flex flex-col gap-3">
                  {r.data.results.map((s) => (
                    <StoryCard key={s.id} story={s} badge={<NewSinceVisit firstSeen={s.first_seen_at} />} />
                  ))}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </Shell>
  );
}
