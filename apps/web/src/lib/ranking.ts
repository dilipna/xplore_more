/** The feed heuristic's reader-tunable weights. Bounds mirror the API's validation (/v1/feed). */

export interface Weights {
  sources: number;
  authority: number;
  hn_points: number;
  half_life_hours: number;
}

export type WeightKey = keyof Weights;

export const DEFAULT_WEIGHTS: Weights = { sources: 1.2, authority: 1.0, hn_points: 0.35, half_life_hours: 18 };

export const KNOBS: { key: WeightKey; param: string; label: string; help: string; min: number; max: number; step: number }[] = [
  {
    key: "sources",
    param: "w_sources",
    label: "Coverage",
    help: "How much it counts when several independent sources report the same story.",
    min: 0,
    max: 3,
    step: 0.1,
  },
  {
    key: "authority",
    param: "w_authority",
    label: "Source authority",
    help: "Weight of the best source's authority (lab and company blogs rate highest).",
    min: 0,
    max: 3,
    step: 0.1,
  },
  {
    key: "hn_points",
    param: "w_points",
    label: "Community points",
    help: "Weight of Hacker News points. Only stories posted there have any.",
    min: 0,
    max: 1.5,
    step: 0.05,
  },
  {
    key: "half_life_hours",
    param: "half_life_hours",
    label: "Freshness half-life",
    help: "A story's score halves every this many hours after publication.",
    min: 2,
    max: 168,
    step: 1,
  },
];

/** Weights from URL search params, clamped to the API's bounds. Null when every knob is at its default. */
export function parseWeights(params: Record<string, string | string[] | undefined>): Weights | null {
  const w: Weights = { ...DEFAULT_WEIGHTS };
  let custom = false;
  for (const k of KNOBS) {
    const raw = params[k.param];
    const value = Number(Array.isArray(raw) ? raw[0] : raw);
    if (raw === undefined || raw === "" || !Number.isFinite(value)) continue;
    const clamped = Math.min(k.max, Math.max(k.min, value));
    w[k.key] = clamped;
    if (clamped !== DEFAULT_WEIGHTS[k.key]) custom = true;
  }
  return custom ? w : null;
}

/** API/URL params for a set of weights; empty for the defaults, so default links stay clean. */
export function weightParams(w: Weights | null): Record<string, string> {
  if (!w) return {};
  const out: Record<string, string> = {};
  for (const k of KNOBS) if (w[k.key] !== DEFAULT_WEIGHTS[k.key]) out[k.param] = String(w[k.key]);
  return out;
}
