# Infrastructure (Terraform, GCP)

All cloud resources are declared here. CI authenticates with **GitHub OIDC → Workload Identity Federation**, so no service-account key exists anywhere.

```
bootstrap/                one-time, applied by a human owner: APIs, state bucket, WIF, CI identities, registry, budget
modules/
  pubsub_pipeline/        topic + DLQ + subscription (push/OIDC or pull) + service-agent IAM + optional BigQuery event log
  cloud_run_service/      Cloud Run service with least-privilege SA, secrets, probes, scaling ceiling
  scheduled_job/          Cloud Run job + Cloud Scheduler trigger
environments/
  prod/                   the always-on system, shaped to fit free tiers
```

## Identity model

| Principal | Can do | Restricted by |
|---|---|---|
| `gh-deployer` | converge `environments/prod` | token exchange only for this repository (+ immutable repo id); impersonation only from `refs/heads/main` |
| `gh-planner` | read resources and state for `terraform plan` on pull requests | narrow viewer roles; state read-only (`plan -lock=false`) |
| `xm-poller` | publish `article-discovered`; read/write its state object | topic-level and bucket-level bindings |
| `xm-ingestor` | publish `article-extracted`; **create** text objects | no database secret, cannot read or delete text |
| `xm-indexer` | pull `article-extracted`; read text; read `database-url` secret | secret-level binding |
| `xm-pubsub-push` | invoke the ingestor | `roles/run.invoker` on that one service |
| `xm-scheduler` | run the four jobs | job-level invoker bindings |
| `xm-api` | serve public reads; read `database-url` and `redis-url` secrets | secret-level bindings; no write access anywhere |
| `xm-mcp` | serve the MCP protocol; calls the public API over the internet | no secrets, no database access, no GCP bindings beyond existing |

## First-time setup

```bash
# 1. Create a GCP project and link billing (the $300 credit clock starts now).
gcloud auth application-default login

# 2. Bootstrap with local state.
cd infra/terraform/bootstrap
terraform init
terraform apply -var project_id=YOUR_PROJECT -var github_repository_id=$(gh api repos/dilipna/xploremore --jq .id)

# 3. Move bootstrap state into the bucket it created.
terraform init -migrate-state -backend-config="bucket=YOUR_PROJECT-tfstate" -backend-config="prefix=bootstrap"
#    (add `backend "gcs" {}` to versions.tf first)

# 4. Store GitHub repository variables from the outputs (Settings -> Secrets and variables ->
#    Actions -> Variables). ci.yml needs none of these; deploy.yml (below) needs all of them:
#    GCP_PROJECT_ID, GCP_REGION, GCP_WORKLOAD_IDENTITY_PROVIDER, GCP_DEPLOYER_SA, GCP_PLANNER_SA,
#    GCP_STATE_BUCKET (= state_bucket output), GCP_ARTIFACT_REGISTRY (= registry output).

# 5. Add secret values (never in Terraform state). author-salt is any random string >= 16
#    chars (the poller refuses discussion sources without it, same rule as local dev's
#    .data/author_salt) -- generate one, don't reuse the local dev value across environments.
printf '%s' "$NEON_POOLED_URL" | gcloud secrets versions add database-url --data-file=-
printf '%s' "$UPSTASH_REDIS_URL" | gcloud secrets versions add redis-url --data-file=-
python3 -c "import secrets; print(secrets.token_hex(24))" | gcloud secrets versions add author-salt --data-file=-

# 6. Apply the environment.
cd ../environments/prod
terraform init -backend-config="bucket=YOUR_PROJECT-tfstate"
terraform apply -var project_id=YOUR_PROJECT
```

## Deploying (`.github/workflows/deploy.yml`)

Runs automatically after `ci.yml` goes green on `main`, or on demand
(`gh workflow run deploy.yml`). Builds and pushes each service image (edge, indexer, api, mcp),
signs it keylessly with cosign (OIDC, no stored key), Trivy-scans the pushed digest, applies
Terraform with the new digests, then canaries the public API specifically: a new revision is
deployed at 0% traffic, smoke-checked on its own per-revision URL (`/readyz`), and only then cut
over to 100% traffic. Everything else — the ingestor, all four Cloud Run jobs, and the MCP
server — has no meaningful canary risk (stateless, no warm-up), so Terraform's own rolling
update is enough for them.

**Not yet run.** It needs the GCP project, Neon and Upstash to exist and the repository
variables above to be set — none of which has happened yet (tracked in the main repo's
`CONTINUE_SESSION.md` §7). It has been validated with `actionlint`, and both the API and MCP
Dockerfiles have been built and run locally against the real stack: the API's `/healthz` and
`/readyz` both returned 200 against real Postgres and Redis; the MCP server answered a real MCP
`initialize` call over streamable HTTP with 200, and a plain `GET /mcp` (its Cloud Run health
probe path) also returns 200. The workflow itself is unexercised until the GCP infrastructure
exists.

## Documented exceptions to security scanners

Each is an inline `#checkov:skip` with its reason:

- **Customer-managed encryption keys:** not used. The data is public news, and KMS keys add per-key cost and rotation work.
- **Bucket access logs:** replaced by Cloud Audit Logs, to stay inside free-tier storage.
- **Versioning on the text bucket:** off. Objects are content-addressed and create-only, so versioning adds no recovery value.
- **Deployer project-level IAM admin:** required to manage per-workload identities. It is mitigated by the branch restriction and environment protection.
