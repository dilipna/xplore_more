import Link from "next/link";
import { snapshot } from "@/lib/recorded-api";
export function CaptureBanner() {
  const date = new Date(snapshot.captured_at).toLocaleString("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  });
  return (
    <aside
      aria-label="Data freshness"
      className="border-b border-amber-400/20 bg-amber-400/5 px-5 py-2.5 text-center text-xs leading-relaxed text-fg-200"
    >
      <span className="mr-2 font-mono text-[10px] uppercase tracking-widest text-amber-300">
        Recorded capture
      </span>
      {date} UTC · {snapshot.coverage.exported_stories} source-linked stories ·{" "}
      {snapshot.coverage.exported_problems} machine-classified problem
      hypotheses.{" "}
      <Link
        href="/capture"
        className="whitespace-nowrap text-amber-300 underline underline-offset-4"
      >
        Data & limitations ↗
      </Link>
    </aside>
  );
}
