# Trusted discovery: local engineering evidence

Status: local development, October 22, 2026. No new publication, remote CI,
production deployment or cloud resource creation is claimed.

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

Interactive/responsive browser QA remains incomplete. Automatic approval review
blocked opening the localhost preview because its usage limit was reached.
No screenshot, responsive pass, successful browser export or production readiness
is claimed. Do not promote this release until browser verification is complete.

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
