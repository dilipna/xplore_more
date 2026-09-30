import type { PulseResponse } from "@/lib/api";
import { formatCount } from "@/lib/format";

/** Items per hour for the last 72 hours (articles green, discussions amber), from /v1/pulse. */
export function PulseChart({ data }: { data: PulseResponse }) {
  const b = data.buckets;
  const max = Math.max(1, ...b.map((x) => x.articles + x.discussions));
  const articles = b.reduce((s, x) => s + x.articles, 0);
  const discussions = b.reduce((s, x) => s + x.discussions, 0);
  const W = 720;
  const H = 110;
  const bw = W / b.length;
  const peak = b.reduce((best, x) => (x.articles + x.discussions > best.articles + best.discussions ? x : best), b[0]);
  return (
    <figure className="min-w-0">
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-fg-500">
        <span className="font-semibold text-fg-200">The last 72 hours, hour by hour</span>
        <span className="font-mono">
          <span className="text-signal-400">{formatCount(articles)} articles</span> ·{" "}
          <span className="text-amber-300">{formatCount(discussions)} discussions</span>
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="mt-2 h-24 w-full" role="img" aria-label={`Items per hour over 72 hours; peak ${peak ? peak.articles + peak.discussions : 0} in one hour`}>
        <defs>
          <linearGradient id="pulse-a" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#b3ffcb" />
            <stop offset="1" stopColor="#14e061" stopOpacity="0.35" />
          </linearGradient>
          <filter id="pulse-glow">
            <feGaussianBlur stdDeviation="2.2" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="rgb(57 255 127 / 0.06)" />
        ))}
        <g filter="url(#pulse-glow)">
          {b.map((x, i) => {
            const ha = (x.articles / max) * (H - 6);
            const hd = (x.discussions / max) * (H - 6);
            return (
              <g key={x.hour}>
                <title>{`${new Date(x.hour).toLocaleString("en-US", { weekday: "short", hour: "numeric" })}: ${x.articles} articles, ${x.discussions} discussions`}</title>
                <rect x={i * bw + 1} y={H - ha} width={Math.max(1, bw - 2)} height={ha} rx="1.5" fill="url(#pulse-a)" />
                <rect x={i * bw + 1} y={H - ha - hd} width={Math.max(1, bw - 2)} height={hd} rx="1.5" fill="#ffb547" opacity="0.85" />
              </g>
            );
          })}
        </g>
      </svg>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-fg-600">
        <span>72 h ago</span>
        <span>by publish time</span>
        <span>now</span>
      </div>
    </figure>
  );
}
