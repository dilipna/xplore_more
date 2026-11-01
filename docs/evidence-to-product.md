# Evidence workbench and Pro2Pro handoff

`/workbench` keeps the original public report next to an editable product scope.
A current record can be opened from `/problems/{id}` with **Draft a product brief**.
The export uses a versioned JSON Schema shared with Pro2Pro. It is a draft, not
human approval or a verified claim of customer demand.

A recorded edition of this workbench is also packaged into Pro2Pro's existing web
application at `/discover` for a public walkthrough. It is explicitly historical:
there is no live XploreMore API behind that edition. The full XploreMore news,
semantic map and discovery service remain a separate application. The newer
standalone recorded edition uses its own dated pipeline capture; Pro2Pro's
historical example remains unchanged. All editions use the same brief contract
and retain links to original source reports. No cloud resources are provisioned
for this feature. See [operating modes](operating-modes.md).

## User journey

1. Inspect a reported problem and open the original source.
2. Define the intended user, goal, included/excluded scope and observable acceptance criteria.
3. Validate and export the brief. Nothing is sent to Pro2Pro automatically.
4. Import it in Pro2Pro `/workspace` and inspect the exact same evidence and scope.
5. A local review rehearsal can record a browser-session decision. This has no
   authority to start a backend build; it is labeled separately from operator approval.
6. An authenticated operator can import into the real backend queue, approve the
   snapshot, and explicitly start a configured model build. Functional observations
   and artifact acceptance are separate from idea approval and never auto-publish.

## Contract

`contracts/problem-brief.v1.schema.json` matches Pro2Pro's `ProblemBrief` model.
Provider/browser fixture tests reject schema drift. Browser validation uses the
actual same `parseBrief` implementation used for import/export; its tests cover
missing evidence, non-HTTP source URLs, malformed types, unknown fields, empty scope,
blank acceptance criteria and oversized imports. The backend remains authoritative.

The recorded example uses problem 1614 from the committed September discovery
comparison and a short source excerpt already present in the problem-label corpus.
Its product specification was authored for this demonstration. It does not establish
that a new product was generated or that the original report remains unresolved.
The source records and problem labels are provisional machine-made artifacts.

## No-model local operation

`XM_SEARCH_MODE=lexical` deliberately serves FTS without constructing or warming
an embedding model. Responses retain `dense_unavailable`; the system does not claim
hybrid-quality results in this mode. The default stays `hybrid`. Indexing new content
still needs the normal embedding pipeline; this setting only governs API retrieval.
The workbench's recorded example needs neither an API nor a model.

The tests use real isolated Postgres and Redis, deterministic/precomputed fixture
vectors and the actual ingestion/API code. Synthetic centroids used in manual replay
QA are not semantic-search or map-quality evidence. Historical record dates are not
rewritten to make them appear recent.

For Windows local tests use explicit IPv4 service addresses:

```powershell
$env:XM_TEST_DATABASE_URL='postgresql+psycopg://xm:xm@127.0.0.1:5544/xploremore_test'
$env:XM_REDIS_URL='redis://127.0.0.1:6379/0'
$env:XM_TEST_REDIS_URL='redis://127.0.0.1:6379/0'
uv run pytest -q
uv run pyright
uv run ruff check .
cd apps/web
pnpm install --frozen-lockfile
pnpm test
pnpm lint
pnpm build
```

The normal `scripts/check.sh` continues to exercise Python, Go and web gates.
A dedicated frontend CI job now checks the browser contract, lint and production build.
Go CI retains its race and fuzz checks. GCP apply remains an explicit manual workflow;
this release does not activate paid hosting or apply Terraform.

## What is not established

No independent human labels, customer usefulness, new clustering/search gains or
improved discovery-source quality are claimed. The stored 16-trial comparison reports
5/8 completed XploreMore research turns versus 7/8 HN/web turns. Rate limits and
failed turns complicate interpretation; model conviction is not a human quality rating.
No paid inference or fresh base/fine-tuned comparison was run.
