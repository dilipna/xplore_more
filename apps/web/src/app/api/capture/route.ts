/** Download the exact canonical JSON bytes, preserving the published checksum. */
export function GET() {
  // A standalone server may expose its internal bind host in request.url.
  // Keep the redirect relative so the browser retains the public origin.
  return new Response(null, {
    status: 307,
    headers: { Location: "/capture-data/xploremore-capture.json" },
  });
}
