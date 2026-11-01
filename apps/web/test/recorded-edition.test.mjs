import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import {
  snapshot,
  recordedFeed,
  recordedResult,
} from "../src/lib/recorded-api.ts";
import { recordedMode } from "../src/lib/web-mode.ts";
import { DEFAULT_WEIGHTS } from "../src/lib/ranking.ts";
import manifest from "../src/data/demo-snapshot.manifest.json" with { type: "json" };
import golden from "./fixtures/recorded-rank-golden.json" with { type: "json" };

test("capture identity and coverage match its packaged records", async () => {
  const text = (
    await readFile(
      new URL("../src/data/demo-snapshot.json", import.meta.url),
      "utf8",
    )
  ).replace(/\r\n/g, "\n");
  assert.equal(
    createHash("sha256").update(text).digest("hex"),
    manifest.snapshot_sha256,
  );
  assert.equal(snapshot.coverage.exported_stories, snapshot.stories.length);
  assert.equal(snapshot.coverage.exported_problems, snapshot.problems.length);
  assert.deepEqual(snapshot.feed.weights, DEFAULT_WEIGHTS);
  assert.ok(Date.parse(snapshot.captured_at));
  for (const field of ["author_hash", "text_uri", "api_key"])
    assert.ok(!text.includes(`"${field}"`));
});
test("every map point and feed card has an inspectable detail and HTTP source", () => {
  const stories = new Set(snapshot.stories.map((d) => d.story.id));
  const problems = new Set(snapshot.problems.map((p) => p.id));
  assert.equal(stories.size, snapshot.stories.length);
  assert.equal(problems.size, snapshot.problems.length);
  for (const p of snapshot.map.points)
    assert.ok((p.kind === "story" ? stories : problems).has(p.id));
  for (const s of snapshot.feed.results) assert.ok(stories.has(s.id));
  for (const url of [
    ...snapshot.stories.flatMap((s) => s.articles.map((a) => a.url)),
    ...snapshot.problems.flatMap((p) => p.evidence.map((e) => e.url)),
  ]) {
    const source = new URL(url);
    assert.ok(["https:", "http:"].includes(source.protocol));
    assert.equal(source.username, "");
    assert.equal(source.password, "");
  }
  for (const p of snapshot.problems) {
    assert.ok(p.evidence.length);
    for (const e of p.evidence) assert.ok(e.excerpt.split(/\s+/).length <= 21);
  }
});
test("default full-window ranking preserves the captured API order", () => {
  assert.deepEqual(
    recordedFeed({ window_hours: 336, limit: 50 }).results.map((s) => s.id),
    snapshot.feed.results.map((s) => s.id),
  );
});
for (const c of golden.cases)
  test(`ranking sliders agree with existing Python formula: ${c.name}`, () => {
    const result = recordedFeed(c.params).results;
    assert.deepEqual(
      result.map((s) => s.id),
      c.order,
    );
    for (const s of result)
      assert.ok(Math.abs(s.score - c.scores[String(s.id)]) < 1e-12);
  });
test("keyword search returns captured detail links and an honest empty result", () => {
  const row = snapshot.stories[0].story;
  const found = recordedResult("/v1/search", { q: row.title }).data;
  assert.ok(found.results.some((s) => s.id === row.id));
  assert.deepEqual(found.degraded, ["recorded_snapshot", "keyword_only"]);
  assert.deepEqual(
    recordedResult("/v1/search", { q: "zzxxnonexistentterm" }).data.results,
    [],
  );
  assert.equal(recordedResult("/v1/stories/99999999").status, 404);
});
test("responses cannot mutate the next visitor’s evidence", () => {
  const id = snapshot.problems[0].id;
  const a = recordedResult(`/v1/problems/${id}`);
  a.data.statement = "overwritten";
  assert.notEqual(
    recordedResult(`/v1/problems/${id}`).data.statement,
    "overwritten",
  );
});
test("only explicit connected mode opts in to upstream access", () => {
  const previous = process.env.XM_WEB_MODE;
  try {
    for (const mode of [undefined, "recorded", "CONNECTED", "true"]) {
      if (mode === undefined) delete process.env.XM_WEB_MODE;
      else process.env.XM_WEB_MODE = mode;
      assert.equal(recordedMode(), true);
    }
    process.env.XM_WEB_MODE = "connected";
    assert.equal(recordedMode(), false);
  } finally {
    if (previous === undefined) delete process.env.XM_WEB_MODE;
    else process.env.XM_WEB_MODE = previous;
  }
});

test('public download preserves the exact published checksum bytes', async()=>{
 const bytes=await readFile(new URL('../public/capture-data/xploremore-capture.json',import.meta.url));
 assert.equal(createHash('sha256').update(bytes).digest('hex'),manifest.snapshot_sha256);
});
