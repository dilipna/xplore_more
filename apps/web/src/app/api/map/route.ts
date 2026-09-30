// Same-origin proxy so client components can load the map without ever seeing the API key.
import { getMap } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  const result = await getMap();
  if (!result.data) return Response.json({ error: "unavailable" }, { status: 503 });
  return Response.json(result.data, { headers: { "Cache-Control": "public, max-age=300" } });
}
