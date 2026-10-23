# Trusted discovery release: frozen acceptance

2026-10-22. User explicitly transferred ownership from the finished XploreMore
session. Isolated branch improve/trusted-discovery starts at existing PR head
f9d72f89b350cffcd39fd3533ac377557b4c695c. Preserve that work and its ProToPro contract.
Fresh baseline: 171 Python tests, no skips, one dependency warning; Ruff/format,
Pyright, ten web contract tests, lint and production build pass.

## Predeclared engineering checks

1. Inject a real SQL failure after article upsert but before story assignment.
   Applied/discussion/story counters must reflect committed effects only. A failed
   message must be nacked, leave no article/idempotency claim, and remain retryable.
   Exercise both a single failing message and a mixed successful/failing batch.
2. Terminate an actual worker process before outer transaction commit. From another
   connection, verify no committed effect or acknowledgment; replay must apply once.
3. Terminate after outer commit and before acknowledgment. Verify one committed
   effect; replay must be a duplicate with the same durable story and article,
   and may acknowledge the delivery without a second application.
4. Persist scenario receipts including process exit, boundary, event/article/story
   identities, row counts, applied/duplicate counts and acknowledgments. These are
   model-free transport/orchestration checks, not semantic-quality measurements.
5. Reproduce existing retrieval evaluation; retain assistant-label qualifications
   and rejected experiments. No new retrieval-quality claim without a separate
   frozen evaluation.

## Product finish line

A responsive, useful evidence-first website with inspectable data provenance and
functional navigation/search/ranking/brief export. Clearly distinguish local live
services from a public recorded edition; never invent missing source URLs, dates,
coverage counts or semantic vectors. Validate any packaged dataset against its
schema and source hashes. Retain source dates and model/label provenance.

Use zero paid hosting/model calls. Existing deployment workflow remains manual;
no GCP apply, public release or new cloud project until a concrete tested release
is approved. Full final checks, exact source identity, CI, evidence package and
browser verification precede any production promotion. OpsVerse and completed
projects remain outside this active scope.
