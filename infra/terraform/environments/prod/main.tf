locals {
  labels = { system = "ingestion" }
}

# --- Identities: one service account per workload, least privilege --------------------

resource "google_service_account" "workload" {
  for_each = {
    poller      = "Discovers articles; publishes article-discovered"
    ingestor    = "Untrusted zone: fetches pages; no database access"
    indexer     = "Trusted zone: writes Postgres from article-extracted"
    pubsub-push = "Signs OIDC tokens for Pub/Sub push to the ingestor"
    scheduler   = "Triggers Cloud Run jobs"
    api         = "Public read API: search, feed, problems"
  }
  account_id   = "xm-${each.key}"
  display_name = "XploreMore ${each.key}"
  description  = each.value
}

locals {
  sa = { for k, v in google_service_account.workload : k => "serviceAccount:${v.email}" }
}

# --- Storage ---------------------------------------------------------------------------

resource "google_storage_bucket" "text" {
  #checkov:skip=CKV_GCP_62:Cloud Audit Logs cover admin access; per-object access logs would add storage cost on a free-tier budget (ADR-0013)
  #checkov:skip=CKV_GCP_78:Objects are content-addressed and create-only (never overwritten), so versioning adds cost without recovery value
  name                        = "${var.project_id}-article-text"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  lifecycle_rule {
    condition {
      age = var.text_retention_days
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket" "state" {
  #checkov:skip=CKV_GCP_62:Cloud Audit Logs cover admin access; per-object access logs would add storage cost on a free-tier budget (ADR-0013)
  name                        = "${var.project_id}-pipeline-state"
  location                    = upper(var.region)
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true # recover from a bad poller state write
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 10
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }
}

# Ingestor may create text objects but never read, overwrite or delete them.
resource "google_storage_bucket_iam_member" "ingestor_text_create" {
  bucket = google_storage_bucket.text.name
  role   = "roles/storage.objectCreator"
  member = local.sa["ingestor"]
}

resource "google_storage_bucket_iam_member" "indexer_text_read" {
  bucket = google_storage_bucket.text.name
  role   = "roles/storage.objectViewer"
  member = local.sa["indexer"]
}

resource "google_storage_bucket_iam_member" "poller_state" {
  bucket = google_storage_bucket.state.name
  role   = "roles/storage.objectUser" # read + generation-conditioned overwrite of its state object
  member = local.sa["poller"]
}

# --- Secrets (values are added out-of-band; never in Terraform state) --------------------

resource "google_secret_manager_secret" "database_url" {
  secret_id = "database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "indexer_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.sa["indexer"]
}

resource "google_secret_manager_secret_iam_member" "api_database_url" {
  secret_id = google_secret_manager_secret.database_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.sa["api"]
}

# Upstash Redis REST/TCP connection string (rediss://). Value is added out-of-band, same as
# database-url: neither the URL nor its embedded credential ever enters Terraform state.
resource "google_secret_manager_secret" "redis_url" {
  secret_id = "redis-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "api_redis_url" {
  secret_id = google_secret_manager_secret.redis_url.id
  role      = "roles/secretmanager.secretAccessor"
  member    = local.sa["api"]
}

# --- Event log (BigQuery) -----------------------------------------------------------------

resource "google_bigquery_dataset" "events" {
  #checkov:skip=CKV_GCP_81:Google-managed encryption; CMEK adds per-key cost and key-rotation ops unjustified for public news data (ADR-0013)
  dataset_id                      = "xm_events"
  location                        = "US"
  description                     = "Append-only event log fed by Pub/Sub BigQuery subscriptions."
  default_partition_expiration_ms = var.event_log_retention_days * 24 * 60 * 60 * 1000
  delete_contents_on_destroy      = false
}

resource "google_bigquery_table" "events_raw" {
  #checkov:skip=CKV_GCP_80:Google-managed encryption; CMEK adds per-key cost and key-rotation ops unjustified for public news data (ADR-0013)
  dataset_id          = google_bigquery_dataset.events.dataset_id
  table_id            = "events_raw"
  deletion_protection = true

  time_partitioning {
    type  = "DAY"
    field = "publish_time"
  }
  clustering = ["subscription_name"]

  # Layout required by BigQuery subscriptions with write_metadata=true.
  schema = jsonencode([
    { name = "subscription_name", type = "STRING", mode = "NULLABLE" },
    { name = "message_id", type = "STRING", mode = "NULLABLE" },
    { name = "publish_time", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "data", type = "STRING", mode = "NULLABLE" },
    { name = "attributes", type = "STRING", mode = "NULLABLE" },
  ])
}

data "google_project" "this" {
  project_id = var.project_id
}

resource "google_bigquery_table_iam_member" "pubsub_writes_event_log" {
  dataset_id = google_bigquery_dataset.events.dataset_id
  table_id   = google_bigquery_table.events_raw.table_id
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

locals {
  event_log_table = "${var.project_id}.${google_bigquery_dataset.events.dataset_id}.${google_bigquery_table.events_raw.table_id}"
}

# --- Ingestor (untrusted zone) -----------------------------------------------------------

module "ingestor" {
  source                = "../../modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  name                  = "xm-ingestor"
  image                 = var.edge_image
  service_account_email = google_service_account.workload["ingestor"].email
  ingress               = "INGRESS_TRAFFIC_INTERNAL_ONLY" # reachable by Pub/Sub push, not the internet
  max_instances         = 3                               # bounds politeness: per-host limits are per instance
  concurrency           = 20
  memory                = "512Mi"
  request_timeout       = "60s"
  labels                = local.labels
  env = {
    XM_GCP_PROJECT             = var.project_id
    XM_TEXT_BUCKET             = google_storage_bucket.text.name
    XM_TOPIC_ARTICLE_EXTRACTED = module.extracted.topic_name
  }
  invoker_members = [local.sa["pubsub-push"]]
}

# --- Pipelines ---------------------------------------------------------------------------

module "discovered" {
  source                     = "../../modules/pubsub_pipeline"
  project_id                 = var.project_id
  name                       = "article-discovered"
  consumer                   = "ingestor"
  push_endpoint              = "${module.ingestor.uri}/push/article-discovered"
  push_service_account_email = google_service_account.workload["pubsub-push"].email
  push_audience              = module.ingestor.uri
  ack_deadline_seconds       = 90 # above the ingestor's 60s request timeout
  publisher_members          = [local.sa["poller"]]
  bigquery_table             = local.event_log_table
  labels                     = local.labels
  depends_on                 = [google_bigquery_table_iam_member.pubsub_writes_event_log]
}

module "extracted" {
  source               = "../../modules/pubsub_pipeline"
  project_id           = var.project_id
  name                 = "article-extracted"
  consumer             = "indexer"
  ack_deadline_seconds = 300 # a micro-batch embeds up to 200 documents before acking
  publisher_members    = [local.sa["ingestor"]]
  subscriber_members   = [local.sa["indexer"]]
  bigquery_table       = local.event_log_table
  labels               = local.labels
  depends_on           = [google_bigquery_table_iam_member.pubsub_writes_event_log]
}

# Pub/Sub must be able to mint OIDC tokens as the push identity.
resource "google_service_account_iam_member" "pubsub_agent_token_creator" {
  service_account_id = google_service_account.workload["pubsub-push"].name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

# --- Scheduled jobs ------------------------------------------------------------------------

module "poller" {
  source                          = "../../modules/scheduled_job"
  project_id                      = var.project_id
  region                          = var.region
  name                            = "xm-poller"
  image                           = var.edge_image
  command                         = ["/app/poller"]
  schedule                        = var.poller_schedule
  service_account_email           = google_service_account.workload["poller"].email
  scheduler_service_account_email = google_service_account.workload["scheduler"].email
  task_timeout                    = "300s"
  labels                          = local.labels
  env = {
    XM_GCP_PROJECT              = var.project_id
    XM_STATE_BUCKET             = google_storage_bucket.state.name
    XM_TOPIC_ARTICLE_DISCOVERED = module.discovered.topic_name
  }
}

module "indexer" {
  source                          = "../../modules/scheduled_job"
  project_id                      = var.project_id
  region                          = var.region
  name                            = "xm-indexer"
  image                           = var.indexer_image
  args                            = ["run", "--max-batches", "25"]
  schedule                        = var.indexer_schedule
  service_account_email           = google_service_account.workload["indexer"].email
  scheduler_service_account_email = google_service_account.workload["scheduler"].email
  task_timeout                    = "900s"
  memory                          = "2Gi" # ONNX embedding model + batch
  labels                          = local.labels
  env = {
    XM_GCP_PROJECT                   = var.project_id
    XM_SUB_ARTICLE_EXTRACTED_INDEXER = module.extracted.subscription_name
    XM_DB_POOL_SIZE                  = "2"
  }
  secret_env = {
    XM_DATABASE_URL = google_secret_manager_secret.database_url.secret_id
  }
}

# --- Public API -----------------------------------------------------------------------

module "api" {
  source                = "../../modules/cloud_run_service"
  project_id            = var.project_id
  region                = var.region
  name                  = "xm-api"
  image                 = var.api_image
  service_account_email = google_service_account.workload["api"].email
  ingress               = "INGRESS_TRAFFIC_ALL" # public read API
  min_instances         = 0                     # free-tier: scales to zero between requests
  max_instances         = var.api_max_instances # hard cost ceiling
  concurrency           = 40
  cpu                   = "1"
  memory                = "1Gi" # embedding model + query-time inference
  request_timeout       = "30s"
  health_path           = "/healthz"
  labels                = local.labels
  env = {
    XM_GCP_PROJECT          = var.project_id
    XM_ENTITIES_FILE        = "/app/config/entities.yaml"
    XM_ANON_RATE_PER_MINUTE = tostring(var.api_anon_rate_per_minute)
  }
  secret_env = {
    XM_DATABASE_URL = google_secret_manager_secret.database_url.secret_id
    XM_REDIS_URL    = google_secret_manager_secret.redis_url.secret_id
  }
  # Read endpoints are public by design (search/feed/problems); auth and rate limiting are
  # enforced in the app (xm_api.auth / xm_api.ratelimit), not at the network edge.
  invoker_members = ["allUsers"]
}
