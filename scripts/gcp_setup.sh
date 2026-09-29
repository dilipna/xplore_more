#!/usr/bin/env bash
# One-time GCP setup, meant for Google Cloud Shell (gcloud is already logged in there).
#
#   git clone https://github.com/dilipna/xploremore.git && cd xploremore
#   bash scripts/gcp_setup.sh YOUR_PROJECT_ID [BILLING_ACCOUNT_ID]
#
# 1. Applies infra/terraform/bootstrap (APIs, state bucket, keyless GitHub OIDC identities,
#    Artifact Registry, optional budget) and moves its state into the bucket it created.
# 2. Creates the four Secret Manager secrets and asks for their values. Nothing is echoed and
#    nothing enters Terraform state. They must exist before the first deploy, because Cloud Run
#    refuses to start a service whose secret has no version.
# 3. Prints the GitHub repository variables deploy.yml needs.
# Safe to re-run: Terraform converges, and existing secret values are kept unless you type a new one.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROJECT="${1:?usage: bash scripts/gcp_setup.sh PROJECT_ID [BILLING_ACCOUNT_ID]}"
BILLING="${2:-}"
REPO="${GITHUB_REPOSITORY:-dilipna/xploremore}"
REGION="${REGION:-us-central1}"
TF_VERSION="1.16.2"

say() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }

say "Project $PROJECT, region $REGION, repo $REPO"
gcloud config set project "$PROJECT" >/dev/null

# Terraform: the repo pins >= 1.16. Cloud Shell's preinstalled one may be older.
if ! terraform version -json 2>/dev/null | grep -q "\"terraform_version\": \"1\.1[6-9]"; then
  say "Installing Terraform $TF_VERSION into ~/bin"
  mkdir -p ~/bin
  curl -fsSLo /tmp/tf.zip "https://releases.hashicorp.com/terraform/${TF_VERSION}/terraform_${TF_VERSION}_linux_amd64.zip"
  unzip -o -q /tmp/tf.zip -d ~/bin
  export PATH="$HOME/bin:$PATH"
fi
terraform version | head -1

say "Looking up the immutable GitHub repository id"
REPO_ID=$(curl -fsS "https://api.github.com/repos/$REPO" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" || true)
if [ -z "$REPO_ID" ]; then
  read -rp "Couldn't read it (private repo?). Paste the numeric repo id, or press Enter to skip: " REPO_ID
fi
echo "repository id: ${REPO_ID:-<none>}"

say "1/3 Bootstrap (APIs, state bucket, OIDC identities, registry)"
cd infra/terraform/bootstrap
BUCKET="${PROJECT}-tfstate"
if gcloud storage buckets describe "gs://$BUCKET" >/dev/null 2>&1 && [ -f backend.tf ]; then
  terraform init -input=false -backend-config="bucket=$BUCKET" -backend-config="prefix=bootstrap" >/dev/null
else
  terraform init -input=false >/dev/null
fi
terraform apply -input=false -auto-approve \
  -var "project_id=$PROJECT" -var "region=$REGION" -var "github_repository=$REPO" \
  -var "github_repository_id=$REPO_ID" -var "billing_account_id=$BILLING"
if [ ! -f backend.tf ]; then
  say "Moving bootstrap state into gs://$BUCKET"
  printf 'terraform {\n  backend "gcs" {}\n}\n' > backend.tf
  terraform init -input=false -migrate-state -force-copy \
    -backend-config="bucket=$BUCKET" -backend-config="prefix=bootstrap" >/dev/null
fi
WIF=$(terraform output -raw workload_identity_provider)
DEPLOYER=$(terraform output -raw deployer_service_account)
PLANNER=$(terraform output -raw planner_service_account)
REGISTRY=$(terraform output -raw registry)
cd ../environments/prod

say "2/3 Secrets"
terraform init -input=false -backend-config="bucket=$BUCKET" >/dev/null
terraform apply -input=false -auto-approve -var "project_id=$PROJECT" -var "region=$REGION" \
  -target=google_secret_manager_secret.database_url \
  -target=google_secret_manager_secret.redis_url \
  -target=google_secret_manager_secret.author_salt \
  -target=google_secret_manager_secret.web_api_key >/dev/null

add_secret() { # name, prompt, transform
  local name="$1" prompt="$2" value have
  have=$(gcloud secrets versions list "$name" --filter="state=ENABLED" --format="value(name)" --limit=1 2>/dev/null || true)
  if [ -n "$have" ]; then
    read -rsp "$prompt [already set; Enter keeps it]: " value; echo
  else
    while [ -z "${value:-}" ]; do read -rsp "$prompt: " value; echo; done
  fi
  [ -z "$value" ] && return 0
  [ "$name" = "database-url" ] && value=$(printf '%s' "$value" | sed -E 's#^postgres(ql)?://#postgresql+psycopg://#')
  printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=- >/dev/null
  echo "  $name: new version added"
}
echo "Paste each value and press Enter (input is hidden)."
add_secret database-url "Neon POOLED connection string (postgresql://...-pooler...)"
add_secret redis-url "Upstash Redis URL (rediss://default:...@...:6379)"
add_secret author-salt "Author salt (contents of .data/author_salt on the laptop)"
add_secret web-api-key "Website API key (contents of .data/web_api_key on the laptop)"

say "3/3 Add these in GitHub: $REPO -> Settings -> Secrets and variables -> Actions -> Variables tab"
cat <<EOF

  GCP_PROJECT_ID                  $PROJECT
  GCP_REGION                      $REGION
  GCP_WORKLOAD_IDENTITY_PROVIDER  $WIF
  GCP_DEPLOYER_SA                 $DEPLOYER
  GCP_PLANNER_SA                  $PLANNER
  GCP_STATE_BUCKET                $BUCKET
  GCP_ARTIFACT_REGISTRY           $REGISTRY

Then: Actions -> deploy -> Run workflow (branch: main).
EOF
