"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { follow, MAX_FOLLOWS, normalizeTopic, onFollowsChange, previousVisit, readFollows, unfollow } from "@/lib/follows";

function useFollows(): string[] | null {
  const [topics, setTopics] = useState<string[] | null>(null); // null until read on the client
  useEffect(() => {
    const sync = () => setTopics(readFollows());
    const first = setTimeout(sync, 0);
    const stop = onFollowsChange(sync);
    return () => {
      clearTimeout(first);
      stop();
    };
  }, []);
  return topics;
}

const BUTTON =
  "inline-flex h-9 items-center gap-1.5 rounded-full border px-4 text-sm font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-400 disabled:cursor-not-allowed disabled:opacity-40";

/** Follow or unfollow a search topic. Stored in this browser only. */
export function FollowButton({ topic }: { topic: string }) {
  const topics = useFollows();
  const t = normalizeTopic(topic);
  if (topics === null || !t) return null;
  const following = topics.includes(t);
  const full = !following && topics.length >= MAX_FOLLOWS;
  return (
    <button
      type="button"
      onClick={() => (following ? unfollow(t) : follow(t))}
      disabled={full}
      title={full ? `You can follow up to ${MAX_FOLLOWS} topics` : "Saved in this browser only"}
      aria-pressed={following}
      className={`${BUTTON} ${
        following
          ? "border-signal-400 bg-signal-400/10 text-signal-400 hover:bg-signal-400/20"
          : "border-field-600 text-fg-200 hover:border-signal-400 hover:text-signal-300"
      }`}
    >
      {following ? "Following" : "Follow"}
    </button>
  );
}

/** On /topics with no topics in the URL: load the follows from this browser into the URL. */
export function TopicsLoader({ current }: { current: string[] }) {
  const topics = useFollows();
  const router = useRouter();
  const want = (topics ?? []).join("\n");
  useEffect(() => {
    if (topics === null || want === current.join("\n")) return;
    const qs = new URLSearchParams(topics.map((t) => ["t", t]));
    router.replace(topics.length ? `/topics?${qs}` : "/topics");
  }, [topics, want, current, router]);

  if (topics === null) return <p className="text-sm text-fg-500">Loading your topics…</p>;
  if (topics.length === 0)
    return (
      <div className="panel p-6 text-sm leading-relaxed text-fg-400">
        <p className="text-fg-200">You don&apos;t follow any topics yet.</p>
        <p className="mt-2">
          Search for something, for example{" "}
          <Link href="/search?q=vllm" className="text-signal-400 hover:underline">
            vllm
          </Link>
          , and press <span className="font-semibold text-fg-200">Follow</span>. You can follow up to {MAX_FOLLOWS}{" "}
          topics.
        </p>
      </div>
    );
  return null;
}

/** "New" marker for stories first seen after the reader's previous visit to My topics. */
export function NewSinceVisit({ firstSeen }: { firstSeen: string }) {
  const [fresh, setFresh] = useState(false);
  useEffect(() => {
    const prev = previousVisit();
    const show = setTimeout(() => setFresh(prev !== null && new Date(firstSeen).getTime() > prev), 0);
    return () => clearTimeout(show);
  }, [firstSeen]);
  if (!fresh) return null;
  return (
    <span className="rounded-full border border-signal-400/40 bg-signal-400/10 px-2 py-0.5 text-[11px] font-semibold text-signal-400">
      New since your last visit
    </span>
  );
}

export function UnfollowLink({ topic }: { topic: string }) {
  return (
    <button
      type="button"
      onClick={() => unfollow(topic)}
      className="text-xs font-semibold text-fg-500 hover:text-signal-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-signal-400"
    >
      Unfollow
    </button>
  );
}
