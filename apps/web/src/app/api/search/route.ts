// Same-origin proxy for the command palette's search-as-you-type (the API key stays on the server).
import { search } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const q = new URL(request.url).searchParams.get("q")?.trim().slice(0, 256) ?? "";
  if (!q) return Response.json({ results: [] });
  const result = await search(q, 8);
  if (!result.data) return Response.json({ results: [], error: "unavailable" }, { status: 503 });
  return Response.json({ results: result.data.results, degraded: result.data.degraded });
}
