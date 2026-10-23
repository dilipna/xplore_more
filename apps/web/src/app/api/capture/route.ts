/** Download the exact canonical JSON bytes, preserving the published checksum. */
export function GET(request: Request) {
  return Response.redirect(new URL("/capture-data/xploremore-capture.json", request.url), 307);
}
