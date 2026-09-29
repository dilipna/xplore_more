import type { ProblemCategory } from "./api";

export function relativeTime(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "—";
  const seconds = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 60) return `${days}d ago`;
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

export const CATEGORY_LABEL: Record<ProblemCategory, string> = {
  bug_or_reliability: "Bug / reliability",
  cost_or_performance: "Cost / performance",
  missing_capability: "Missing capability",
  workflow_friction: "Workflow friction",
};

export const CATEGORIES = Object.keys(CATEGORY_LABEL) as ProblemCategory[];

export function categoryLabel(category: ProblemCategory | null): string {
  return category ? CATEGORY_LABEL[category] : "Uncategorized";
}

const PLATFORM: Record<string, { label: string; color: string }> = {
  hn: { label: "Hacker News", color: "var(--color-hn)" },
  github: { label: "GitHub", color: "var(--color-github)" },
  lobsters: { label: "Lobsters", color: "var(--color-lobsters)" },
  stackexchange: { label: "Stack Exchange", color: "var(--color-stackexchange)" },
};

export function platformInfo(platform: string): { label: string; color: string } {
  return PLATFORM[platform] ?? { label: platform, color: "var(--color-fg-400)" };
}

const norm = (s: string) => s.replace(/\s+/g, " ").trim().toLowerCase();

/** True when an evidence excerpt is just the problem statement again (same post). */
export function echoesStatement(statement: string, excerpt: string): boolean {
  return norm(excerpt).startsWith(norm(statement).slice(0, 60));
}

/**
 * Statements are stored cut at 280 characters (xm_problems.assign.STATEMENT_CHARS). When the
 * source post visibly continues past the statement, mark the cut instead of ending mid-word.
 */
export function displayStatement(statement: string, excerpts: string[]): string {
  const s = statement.trim();
  const cut = excerpts.some((e) => {
    const n = norm(e);
    return n.length > norm(s).length + 1 && n.startsWith(norm(s).slice(0, -1));
  });
  return cut && !/[.!?…)"']$/.test(s) ? `${s}…` : s;
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}

/** True when the timestamp is within the last `ms` milliseconds (e.g. a "New" badge). */
export function isRecent(iso: string | null | undefined, ms: number, now: Date = new Date()): boolean {
  return !!iso && now.getTime() - new Date(iso).getTime() < ms;
}
