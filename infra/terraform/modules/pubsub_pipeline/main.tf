terraform {
  required_version = ">= 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.2"
    }
  }
}

data "google_project" "this" {
  project_id = var.project_id
}

locals {
  pubsub_agent = "serviceAccount:service-${data.google_project.this.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
  is_push      = var.push_endpoint != null
}

resource "google_pubsub_topic" "main" {
  #checkov:skip=CKV_GCP_83:Google-managed encryption; CMEK adds per-key cost and key-rotation ops unjustified for public news data (ADR-0013)
  project                    = var.project_id
  name                       = var.name
  message_retention_duration = var.topic_retention # enables seek-to-timestamp replay
  labels                     = var.labels
}

resource "google_pubsub_topic" "dlq" {
  #checkov:skip=CKV_GCP_83:Google-managed encryption; CMEK adds per-key cost and key-rotation ops unjustified for public news data (ADR-0013)
  project = var.project_id
  name    = "${var.name}-dlq"
  labels  = var.labels
}

resource "google_pubsub_subscription" "main" {
  project                    = var.project_id
  name                       = "${var.name}-${var.consumer}"
  topic                      = google_pubsub_topic.main.id
  ack_deadline_seconds       = var.ack_deadline_seconds
  message_retention_duration = var.subscription_retention # buffer while consumers are down
  labels                     = var.labels

  expiration_policy {
    ttl = "" # never expire an idle subscription (e.g. during an indexer outage)
  }

  retry_policy {
    minimum_backoff = var.min_backoff
    maximum_backoff = var.max_backoff
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dlq.id
    max_delivery_attempts = var.max_delivery_attempts
  }

  dynamic "push_config" {
    for_each = local.is_push ? [1] : []
    content {
      push_endpoint = var.push_endpoint
      oidc_token {
        service_account_email = var.push_service_account_email
        audience              = var.push_audience
      }
    }
  }
}

# DLQ messages are retained on a pull subscription for inspection and replay
# (scripts/replay_dlq). Without a subscription, dead-lettered messages would be dropped.
resource "google_pubsub_subscription" "dlq_inspect" {
  project                    = var.project_id
  name                       = "${var.name}-dlq-inspect"
  topic                      = google_pubsub_topic.dlq.id
  message_retention_duration = "604800s"
  ack_deadline_seconds       = 60
  labels                     = var.labels

  expiration_policy {
    ttl = ""
  }
}

# The Pub/Sub service agent forwards to the DLQ and must be able to ack the source
# subscription. Missing either binding silently disables dead-lettering.
resource "google_pubsub_topic_iam_member" "agent_dlq_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.dlq.name
  role    = "roles/pubsub.publisher"
  member  = local.pubsub_agent
}

resource "google_pubsub_subscription_iam_member" "agent_source_subscriber" {
  project      = var.project_id
  subscription = google_pubsub_subscription.main.name
  role         = "roles/pubsub.subscriber"
  member       = local.pubsub_agent
}

resource "google_pubsub_topic_iam_member" "publishers" {
  for_each = toset(var.publisher_members)
  project  = var.project_id
  topic    = google_pubsub_topic.main.name
  role     = "roles/pubsub.publisher"
  member   = each.value
}

resource "google_pubsub_subscription_iam_member" "subscribers" {
  for_each     = toset(var.subscriber_members)
  project      = var.project_id
  subscription = google_pubsub_subscription.main.name
  role         = "roles/pubsub.subscriber"
  member       = each.value
}

# Optional zero-code event log: every message on the topic lands in BigQuery.
resource "google_pubsub_subscription" "bigquery" {
  count   = var.bigquery_table == null ? 0 : 1
  project = var.project_id
  name    = "${var.name}-bigquery"
  topic   = google_pubsub_topic.main.id
  labels  = var.labels

  bigquery_config {
    table          = var.bigquery_table
    write_metadata = true # subscription_name, message_id, publish_time, attributes
  }

  expiration_policy {
    ttl = ""
  }
}
