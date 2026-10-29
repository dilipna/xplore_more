// Production HTTP checks. Run after `pnpm build`; no browser or paid service.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { once } from 'node:events';
import { readFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';

const web = fileURLToPath(new URL('../', import.meta.url));
const snapshot = JSON.parse(await readFile(new URL('../src/data/demo-snapshot.json', import.meta.url)));
const manifest = JSON.parse(await readFile(new URL('../src/data/demo-snapshot.manifest.json', import.meta.url)));
const key = 'local-smoke-key-not-a-credential';
const requests = [];
const upstream = createServer((req, res) => {
  requests.push({ path: req.url, authenticated: req.headers['x-xm-api-key'] === key });
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify({ results: [snapshot.stories[0].story], degraded: [] }));
});
upstream.listen(0, '127.0.0.1');
await once(upstream, 'listening');
const upstreamUrl = `http://127.0.0.1:${upstream.address().port}`;
const servers = [];
async function start(mode) {
  const reservation = createServer();
  reservation.listen(0, '127.0.0.1');
  await once(reservation, 'listening');
  const port = reservation.address().port;
  await new Promise((resolve) => reservation.close(resolve));
  const child = spawn(process.execPath, ['node_modules/next/dist/bin/next', 'start', '--hostname', '127.0.0.1', '--port', String(port)], {
    cwd: web,
    env: { ...process.env, XM_WEB_MODE: mode, XM_API_URL: upstreamUrl, XM_API_KEY: key, NEXT_TELEMETRY_DISABLED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  servers.push(child);
  let output = '';
  child.stdout.on('data', (data) => { output += data; });
  child.stderr.on('data', (data) => { output += data; });
  const origin = `http://127.0.0.1:${port}`;
  for (let attempt = 0; attempt < 120; attempt++) {
    if (child.exitCode !== null) throw new Error(`Server exited: ${output}`);
    try {
      const response = await fetch(`${origin}/healthz`, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return origin;
    } catch { /* Local server is still starting. */ }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`Server did not start: ${output}`);
}
try {
  const recorded = await start('recorded');
  const routes = ['/', '/feed', '/problems', '/map', '/search?q=OlmoEarth', '/topics', '/briefing', '/capture', '/how-it-works',
    `/stories/${snapshot.stories[0].story.id}`, `/problems/${snapshot.problems[0].id}`, `/workbench?problem=${snapshot.problems[0].id}`];
  for (const route of routes) {
    const response = await fetch(recorded + route);
    assert.equal(response.status, 200, route);
    const html = await response.text();
    assert.ok(!html.includes(key), `Server-only key leaked at ${route}`);
    assert.equal((html.match(/<main[ >]/g) ?? []).length, 1, route);
    assert.equal((html.match(/<h1[ >]/g) ?? []).length, 1, route);
  }
  for (const route of ['/api/search?q=OlmoEarth', '/api/map', '/rss.xml', '/problems.xml', '/feed.json', '/sitemap.xml']) {
    const response = await fetch(recorded + route);
    assert.equal(response.status, 200, route);
    assert.ok(!(await response.text()).includes(key), route);
  }
  const redirect = await fetch(`${recorded}/api/capture`, { redirect: 'manual' });
  assert.equal(redirect.status, 307);
  assert.equal(redirect.headers.get('location'), '/capture-data/xploremore-capture.json');
  const capture = await fetch(`${recorded}/api/capture`);
  assert.equal(capture.status, 200);
  const captureHash = createHash('sha256').update(Buffer.from(await capture.arrayBuffer())).digest('hex');
  assert.equal(captureHash, manifest.snapshot_sha256);
  assert.equal(requests.length, 0, 'Recorded mode contacted the configured upstream');
  const connected = await start('connected');
  const search = await fetch(`${connected}/api/search?q=smoke-probe`);
  assert.equal(search.status, 200);
  assert.equal((await search.json()).results[0].id, snapshot.stories[0].story.id);
  assert.equal(requests.length, 1);
  assert.ok(requests[0].path.startsWith('/v1/search?'));
  assert.equal(requests[0].authenticated, true);
  await new Promise((resolve) => upstream.close(resolve));
  const unavailable = await fetch(`${connected}/api/search?q=unavailable-probe`);
  assert.equal(unavailable.status, 503, 'Connected mode silently fell back to captured data');
  console.log(JSON.stringify({ routes: routes.length, auxiliaryRoutes: 6, recordedUpstreamRequests: 0, captureHash,
    connectedAuthenticatedProxy: true, unavailableStatus: unavailable.status, scope: 'HTTP production server; browser interaction checked separately' }, null, 2));
} finally {
  for (const child of servers) {
    if (child.exitCode === null) { const ended = once(child, 'exit'); child.kill(); await ended; }
  }
  if (upstream.listening) await new Promise((resolve) => upstream.close(resolve));
}
