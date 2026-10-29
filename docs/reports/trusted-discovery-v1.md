# Trusted discovery: local engineering evidence

Initial local report: October 22, 2026, before publication and remote CI.

October 23 update: the approved revision was published and remote CI exposed
dependency advisories. Hosting remains uncreated. See the subsequent
[security correction and release status](security-release-v1.md); the local
results below describe the initial release and are not a claim that its CI passed.

## A rollback was reported as successful work

The ingestion pipeline updated batch counters inside each message's SQL
savepoint. If story assignment subsequently failed, the database rolled back
the article and idempotency claim but the reported `applied` count stayed
incremented. A successful and failing message in one batch produced the same
accounting defect. Two negative cases reproduced it with a real SQL division
error after article upsert.

The correction accumulates effects per message and adds them to batch counters
only after successful savepoint exit. A failed message is retried; a successful
neighbor keeps its durable effect. This preserves the existing transaction and
acknowledgment design rather than adding a second workflow engine.

## Real process termination, not just mocked exceptions

Three scenarios run the production drain in an actual child process against
Postgres: normal completion, termination before outer commit, and termination
after commit but before acknowledgment. Replay of the same envelope verifies
durable counts, event identities, acknowledgments and stable story/article IDs.
Receipts include child exits and normalized source hashes. Embeddings are
deterministic test inputs: these tests establish transport/database behavior,
not model quality or a global exactly-once guarantee.

The local full Python regression increased from 171 to 176 passing tests with
zero skips. Ruff, formatting and Pyright pass. CI now retains the recovery JSON
receipts as downloadable artifacts; that workflow change has not run remotely.

## Actual bounded collection

The Go poller discovered 51 news items and 28 discussion items. The local
Pub/Sub emulator and Go ingestor produced 71 extracted documents; eight items
ended in permanent fetch/content failures. A transient attempt later succeeded.
The CPU indexer applied 71 documents with zero invalid/failed index messages,
creating 43 stories and admitting 17 problem hypotheses from 28 discussions.
It used the open BAAI/bge-small-en-v1.5 ONNX embedding model locally, with no
paid inference API. These pipeline counts are not an accuracy evaluation.

The website packages 36 stories within its export window and all 17 hypotheses.
Map points must resolve to packaged detail pages. Twenty-word excerpts are
bounded for publication; full source text and pseudonymous author hashes are
excluded. The manifest identifies exact capture bytes and the indexer source.

## Verification scope and remaining work

Nineteen web contracts pass, including capture identity, valid source links,
mutation isolation, map/detail coverage, search behavior, explicit connected
mode, exact download bytes and two ranking parity cases against the existing
Python formula. Final web lint and a production build passed after the semantic
HTML and wording corrections. Formula parity is not evidence of better ranking quality.

Initial browser QA was blocked by an automatic approval-review usage limit.
Access later resumed normally. The production preview was checked at 1440,
768 and 390 pixels: forty route/layout observations had no horizontal overflow,
one main landmark and one page heading. Source details, title search and its empty
state, topic follow/unfollow and persistence after reload, ranking URL updates and
reset, command-palette search/navigation/Escape, and map highlighting/layer
controls worked. A new expandable list exposes all 48 mapped records as ordinary
links; keyboard activation opened the correct record. Desktop and phone
screenshots and the layout observations are retained in the local evidence package.

The workbench rejected an incomplete scope. An actual browser download of a
completed draft passed the shared JSON schema and preserved problem 7, its
original GitHub issue URL and exact October 22 capture timestamp. The temporary
QA scope is test input, not a claim that a compatibility checklist solves that
report. Nothing was sent to Pro2Pro or approved for model execution.

The production-server smoke test checks twelve HTML routes and six auxiliary
routes, server-only credential non-disclosure, exact capture checksum, zero
upstream requests in recorded mode, authenticated proxying in explicit connected
mode, and HTTP 503 when that upstream is unavailable. It now runs after the web
build in CI. Local results pass; remote CI for this revision is still pending.

## A standalone-only redirect defect

The first read-only container smoke check found that `/api/capture` built an
absolute redirect using the server's internal bind host (`0.0.0.0`). This was
invisible when using a localhost Next server. The correction returns a relative
Location header, and the HTTP regression test requires that exact header.
The rebuilt image then passed health, homepage and download checksum checks as
UID 1000 in a read-only container with capabilities dropped. An earlier one-off
Node probe crashed on the host; the subsequent PowerShell check exposed the
redirect defect. Neither failed attempt is counted as a pass.

The accessible Vercel team `asmq333` is on Hobby and lists five existing projects,
none for XploreMore. No new project has been created. Source publication, remote
CI and a separate recorded-site project require approval for the final commit.
No connected backend, model service, GCP resource or paid hosting is proposed.

Historical search results retain their assistant-judged, small-sample and
snapshot limitations. `tools/reproduce_search.py` reruns that experiment into
ignored evidence files without overwriting the committed baseline or model.
The reranker stays disabled by default; unhelpful news/problem links stay rejected.

The complete 62-query experiment was reproduced with all 3,531 judgments. Every
per-query metric matched the committed results exactly (maximum absolute
difference 0.0). The reranker-versus-hybrid nDCG confidence interval still includes
zero, so the decision not to enable it remains unchanged. This reproduction
does not add human validation or measure the new public capture.

A final regression attempt encountered stopped local Docker services and finished
with 110 passes and 66 skips. That attempt is not accepted as release evidence.
Only this chat's named Postgres and Redis containers were restored, followed by
a separate complete rerun. The interrupted log is retained rather than overwritten.
The first restored attempt had three Redis-dependent failures because only
`XM_TEST_REDIS_URL` was set for the nonstandard local port. Application-created
settings also require `XM_REDIS_URL`; its default remains port 6379. Correcting
the invocation configures both to the named local Redis on port 6394. No source
assertions, rate limits or cache checks were weakened to resolve these failures.
The corrected final run passed all 176 tests with zero skips in 52.40 seconds,
with one upstream Starlette/AnyIO deprecation warning.
