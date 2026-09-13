terraform {
  required_version = ">= 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.2"
    }
  }
}

resource "google_cloud_run_v2_service" "this" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  ingress             = var.ingress
  deletion_protection = var.deletion_protection
  labels              = var.labels

  template {
    service_account                  = var.service_account_email
    timeout                          = var.request_timeout
    max_instance_request_concurrency = var.concurrency

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances # hard cost ceiling and downstream-connection budget
    }

    containers {
      image = var.image

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = true # CPU only during requests: free-tier friendly
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = var.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        http_get {
          path = var.health_path
        }
        period_seconds    = 2
        failure_threshold = 30
      }

      liveness_probe {
        http_get {
          path = var.health_path
        }
        period_seconds = 30
      }
    }
  }

  lifecycle {
    # CI deploys new image digests through canary revisions; Terraform owns everything
    # else. Without this, every apply would roll the service back to the variable image.
    ignore_changes = [
      template[0].containers[0].image,
      client,
      client_version,
    ]
  }
}

resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this.name
  role     = "roles/run.invoker"
  member   = each.value
}
