terraform {
  required_version = ">= 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.2"
    }
  }
  # Bootstrap is applied once with local state by a human project owner, then its state
  # file is uploaded to the bucket it created (see README.md). Everything else uses the
  # remote GCS backend and runs from CI through Workload Identity Federation.
}

provider "google" {
  project = var.project_id
  region  = var.region
}
