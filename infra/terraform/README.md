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
| `xm-scheduler` | run the two jobs | job-level invoker bindings |

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

# 4. Store GitHub repository variables from the outputs:
#    GCP_PROJECT_ID, GCP_WORKLOAD_IDENTITY_PROVIDER, GCP_DEPLOYER_SA, GCP_PLANNER_SA

# 5. Add the database URL secret value (never in Terraform state):
printf '%s' "$NEON_POOLED_URL" | gcloud secrets versions add database-url --data-file=-

# 6. Apply the environment.
cd ../environments/prod
terraform init -backend-config="bucket=YOUR_PROJECT-tfstate"
terraform apply -var project_id=YOUR_PROJECT
```

## Documented exceptions to security scanners

Each is an inline `#checkov:skip` with its reason:

- **Customer-managed encryption keys:** not used. The data is public news, and KMS keys add per-key cost and rotation work.
- **Bucket access logs:** replaced by Cloud Audit Logs, to stay inside free-tier storage.
- **Versioning on the text bucket:** off. Objects are content-addressed and create-only, so versioning adds no recovery value.
- **Deployer project-level IAM admin:** required to manage per-workload identities. It is mitigated by the branch restriction and environment protection.
