import type { ProblemCategory } from "@/lib/api";
import { categoryLabel, platformInfo } from "@/lib/format";
import { CATEGORY_LABEL, type SourceCategory, sourceCategory } from "@/lib/sources";

export function Eyebrow({ children }: { children: React.ReactNode }) {
  return <h2 className="text-[15px] font-semibold text-fg-50">{children}</h2>;
}

export function PlatformBadge({ platform }: { platform: string }) {
  const { label, color } = platformInfo(platform);
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border hairline bg-field-850 px-2 py-0.5 text-[11px] text-fg-200">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} aria-hidden="true" />
      {label}
    </span>
  );
}

export function CategoryBadge({ category }: { category: ProblemCategory | null }) {
  return (
    <span className="inline-flex items-center rounded-md border border-amber-400/25 bg-amber-400/8 px-2 py-0.5 text-[11px] text-amber-300">
      {categoryLabel(category)}
    </span>
  );
}

/** A horizontal bar for a value in [0, 1], used for demand (relative to the page max) and relevance. */
export function Meter({ value, label }: { value: number; label: string }) {
  const pct = Math.max(2, Math.min(100, value * 100));
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-field-700" role="meter" aria-label={label} aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full rounded-full bg-gradient-to-r from-signal-700 to-signal-400 shadow-[0_0_10px_rgb(57_255_127/0.55)]" style={{ width: `${pct}%` }} />
    </div>
  );
}

export function Metric({ value, label }: { value: React.ReactNode; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-mono text-lg leading-none text-fg-50 tabular-nums">{value}</span>
      <span className="mt-1.5 text-[11px] text-fg-500">{label}</span>
    </div>
  );
}

export function Unavailable({ what }: { what: string }) {
  return (
    <div className="panel px-6 py-10 text-center">
      <p className="text-fg-200">Couldn&apos;t load {what} right now.</p>
      <p className="mt-2 text-sm text-fg-500">The API didn&apos;t answer. Try again in a few seconds.</p>
    </div>
  );
}

export function PageIntro({ title, children }: { title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <section className="relative overflow-hidden border-b hairline">
      <div className="grid-field pointer-events-none absolute inset-0" aria-hidden="true" />
      <div className="relative mx-auto max-w-6xl px-5 pt-10 pb-8">
        <h1 className="max-w-3xl text-balance text-3xl font-semibold leading-tight tracking-tight text-fg-50 md:text-4xl">
          {title}
        </h1>
        {children}
      </div>
    </section>
  );
}

const SOURCE_BADGE: Record<SourceCategory, string> = {
  primary: "border-signal-400/40 bg-signal-400/10 text-signal-400",
  press: "border-sky-400/30 bg-sky-400/10 text-sky-300",
  independent: "border-violet-400/30 bg-violet-400/10 text-violet-300",
  community: "border-field-600 bg-field-850 text-fg-400",
};

/** Who published it: the primary source (lab, company, project, paper), press, independent or community. */
export function SourceBadge({ id }: { id: string }) {
  const cat = sourceCategory(id);
  if (!cat) return null;
  return (
    <span className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10.5px] font-medium ${SOURCE_BADGE[cat]}`}>
      {CATEGORY_LABEL[cat]}
    </span>
  );
}
