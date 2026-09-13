data "google_project" "this" {
  project_id = var.project_id
}

locals {
  services = [
    "artifactregistry.googleapis.com",
    "bigquery.googleapis.com",
    "billingbudgets.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
    "storage.googleapis.com",
  ]

  # Roles the CI deployer needs to converge environments/prod. This is broad by necessity
  # (it manages IAM bindings), so it is guarded by: repository + ref restriction on the
  # identity, GitHub environment protection rules, and required PR review on main.
  deployer_roles = [
    "roles/artifactregistry.admin",
    "roles/bigquery.admin",
    "roles/cloudscheduler.admin",
    "roles/iam.serviceAccountAdmin",
    "roles/iam.serviceAccountUser",
    "roles/pubsub.admin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/secretmanager.admin",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/storage.admin",
  ]

  planner_roles = [
    "roles/artifactregistry.reader",
    "roles/bigquery.metadataViewer",
    "roles/cloudscheduler.viewer",
    "roles/iam.securityReviewer", # IAM policies on every resource, for plan diffs
    "roles/iam.serviceAccountViewer",
    "roles/pubsub.viewer",
    "roles/run.viewer",
    "roles/secretmanager.viewer", # metadata only; cannot access secret payloads
    "roles/serviceusage.serviceUsageViewer",
    "roles/storage.bucketViewer",
  ]

  oidc_condition = var.github_repository_id == "" ? (
    "assertion.repository == \"${var.github_repository}\""
    ) : (
    "assertion.repository_id == \"${var.github_repository_id}\" && assertion.repository == \"${var.github_repository}\""
  )
}

resource "google_project_service" "enabled" {
  for_each           = toset(local.services)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# --- Remote state -----------------------------------------------------------

resource "google_storage_bucket" "tfstate" {
  #checkov:skip=CKV_GCP_62:Cloud Audit Logs cover admin access; per-object access logs would add storage cost on a free-tier budget (ADR-0013)
  name                        = "${var.project_id}-tfstate"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true # state history: recover from a bad apply or corruption
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 20
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.enabled]
}

# --- Keyless CI identity: GitHub OIDC -> Workload Identity Federation ---------

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github"
  display_name              = "GitHub Actions"
  description               = "OIDC federation for ${var.github_repository}; no service account keys exist."
  depends_on                = [google_project_service.enabled]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  #checkov:skip=CKV_GCP_125:Condition is built in local.oidc_condition and always pins assertion.repository (and repository_id when set); the static check cannot resolve locals
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_id"    = "assertion.repository_id"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
    "attribute.event_name"       = "assertion.event_name"
  }

  # Without a condition ANY GitHub repository could mint tokens against this pool and rely
  # only on IAM bindings to be rejected. Repository *names* can be re-registered after a
  # rename or deletion, so the immutable numeric repository id is pinned when known.
  attribute_condition = local.oidc_condition

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  account_id   = "gh-deployer"
  display_name = "GitHub Actions deployer (main branch only)"
}

resource "google_service_account" "planner" {
  account_id   = "gh-planner"
  display_name = "GitHub Actions planner (pull requests, read-only)"
}

# Only workflows running on the deploy ref of the allowed repository can impersonate the
# deployer. The pool-level condition already pins the repository.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.ref/${var.deploy_ref}"
}

resource "google_service_account_iam_member" "planner_wif" {
  service_account_id = google_service_account.planner.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}

resource "google_project_iam_member" "deployer" {
  #checkov:skip=CKV_GCP_49:Deployer must create runtime service accounts and act as them to deploy; restricted to main branch + protected environment
  #checkov:skip=CKV_GCP_41:Same as CKV_GCP_49; actAs is required to attach service accounts to Cloud Run
  for_each = toset(local.deployer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

# Narrow read-only roles instead of the basic roles/viewer: the planner can read exactly
# the resource types environments/prod manages (plus their IAM policies), nothing else.
resource "google_project_iam_member" "planner" {
  for_each = toset(local.planner_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.planner.email}"
}

# Planner reads state but cannot write it: PR plans run with -lock=false, so a malicious
# PR cannot tamper with state or hold the lock.
resource "google_storage_bucket_iam_member" "planner_state_read" {
  bucket = google_storage_bucket.tfstate.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.planner.email}"
}

# --- Container registry --------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  #checkov:skip=CKV_GCP_84:Google-managed encryption; CMEK adds per-key cost and key-rotation ops unjustified for public news data (ADR-0013)
  repository_id = "xploremore"
  location      = var.region
  format        = "DOCKER"
  description   = "XploreMore service images (signed with cosign in CI)."

  docker_config {
    immutable_tags = true # a tag always means the same image digest
  }

  # Free tier is 0.5 GB: keep a short history and delete untagged layers.
  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }
  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "1209600s" # 14 days
    }
  }

  depends_on = [google_project_service.enabled]
}

# --- Cost guardrail --------------------------------------------------------------

resource "google_billing_budget" "monthly" {
  count           = var.billing_account_id == "" ? 0 : 1
  billing_account = var.billing_account_id
  display_name    = "xploremore-monthly"

  budget_filter {
    projects = ["projects/${data.google_project.this.number}"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = [0.01, 0.1, 0.5, 1.0]
    content {
      threshold_percent = threshold_rules.value
    }
  }

  depends_on = [google_project_service.enabled]
}
