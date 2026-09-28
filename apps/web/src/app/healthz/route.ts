// Liveness for Cloud Run: the process is up. Deliberately does not call the API, so an API
// outage degrades pages (they show an "unavailable" state) instead of restart-looping the site.
export function GET() {
  return Response.json({ status: "ok" });
}
