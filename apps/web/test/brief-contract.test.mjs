import { test } from "node:test";
import assert from "node:assert/strict";
import { parseBrief } from "../src/lib/brief.ts";
import fixture from "../src/data/brief-example.json" with { type: "json" };
const copy = () => JSON.parse(JSON.stringify(fixture));
test("the recorded source snapshot survives the actual browser validator", () => {
  const brief = parseBrief(JSON.stringify(fixture));
  assert.equal(brief.source.problem_id, 1614);
  assert.deepEqual(brief.source.evidence, fixture.source.evidence);
});
for (const [name, change] of [
  ["missing evidence", (b) => (b.source.evidence = [])],
  [
    "non-HTTP evidence URL",
    (b) => (b.source.evidence[0].url = "javascript:alert(1)"),
  ],
  ["missing scope", (b) => delete b.spec],
  ["unbounded scope", (b) => (b.spec.in_scope = Array(7).fill("feature"))],
  ["noninteger reporters", (b) => (b.source.voice_count = true)],
  ["invented approval field", (b) => (b.approved = true)],
  ["missing acceptance", (b) => (b.spec.acceptance = [])],
  ["blank criterion", (b) => (b.spec.acceptance[0].then = "   ")],
])
  test(name + " is rejected before import/export", () => {
    const b = copy();
    change(b);
    assert.throws(() => parseBrief(JSON.stringify(b)));
  });
test("oversized and malformed imports have useful failures", () => {
  assert.throws(() => parseBrief("x".repeat(64001)), /64 KB/);
  assert.throws(() => parseBrief("{"), /valid JSON/);
});
