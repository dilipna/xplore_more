import Ajv from "ajv";
import addFormats from "ajv-formats";
import schema from "../data/problem-brief.v1.schema.json" with { type: "json" };
const ajv = new Ajv({ allErrors: true, strict: false });
addFormats(ajv);
const validate = ajv.compile<Brief>(schema);
export interface Brief {
  schema_version: 1;
  source: {
    system: "xploremore";
    problem_id: number;
    captured_at: string;
    statement: string;
    evidence: { url: string; excerpt: string; title?: string }[];
    voice_count: number;
    source_count: number;
    limitations: string;
  };
  spec: {
    target_user: string;
    goal: string;
    delivery: "browser_tool";
    in_scope: string[];
    out_of_scope: string[];
    acceptance: { given: string; when: string; then: string }[];
  };
}
export function parseBrief(text: string): Brief {
  if (new TextEncoder().encode(text).length > 64000)
    throw new Error("Keep the brief below 64 KB.");
  let value: unknown;
  try {
    value = JSON.parse(text, (_key, v) =>
      typeof v === "string" ? v.trim() : v,
    );
  } catch {
    throw new Error("Choose a valid JSON brief.");
  }
  if (!validate(value)) {
    const e = validate.errors?.[0];
    throw new Error(
      `Brief ${e?.instancePath || "input"}: ${e?.message || "invalid contract"}`,
    );
  }
  return value;
}
export function downloadBrief(brief: Brief) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(brief, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = `xploremore-${brief.source.problem_id}-brief.json`;
  link.click();
  URL.revokeObjectURL(url);
}
