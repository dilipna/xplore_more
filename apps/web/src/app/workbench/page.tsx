import { recordedMode } from "@/lib/web-mode";
import { snapshot } from "@/lib/recorded-api";
import BriefWorkbench from "@/components/brief-workbench";
import { getProblem } from "@/lib/api";
import type { Brief } from "@/lib/brief";
export const dynamic = "force-dynamic";
export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ problem?: string }>;
}) {
  const { problem } = await searchParams;
  let initial: Brief | null = null,
    error = "";
  if (problem) {
    const id = Number(problem);
    if (!Number.isSafeInteger(id) || id < 1)
      error = "Choose a valid positive problem identifier.";
    else {
      const result = await getProblem(id),
        p = result.data;
      if (!p)
        error =
          "The selected problem record could not be loaded. You can inspect a labeled recorded example instead.";
      else if (!p.evidence.length)
        error = "This record has no evidence to carry into a brief.";
      else
        initial = {
          schema_version: 1,
          source: {
            system: "xploremore",
            problem_id: p.id,
            captured_at: recordedMode() ? snapshot.captured_at : new Date().toISOString(),
            statement: p.statement,
            evidence: p.evidence
              .slice(0, 10)
              .map((e) => ({
                url: e.url,
                excerpt: e.excerpt,
                title: "Original public report",
              })),
            voice_count: p.voice_count,
            source_count: p.source_count,
            limitations:
              recordedMode() ? "Recorded local-pipeline capture. Original source dates are retained; classification and clustering are provisional, counts do not establish customer demand, and the source may no longer be unresolved." : "Snapshot from the configured XploreMore API. Machine classification and clustering are provisional; counts do not establish customer demand.",
          },
          spec: {
            target_user: "",
            goal: "",
            delivery: "browser_tool",
            in_scope: [""],
            out_of_scope: [""],
            acceptance: [{ given: "", when: "", then: "" }],
          },
        };
    }
  }
  return <BriefWorkbench initial={initial} loadError={error} />;
}
