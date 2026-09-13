terraform {
  required_version = ">= 1.16.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.2"
    }
  }

  # Partial configuration: terraform init -backend-config=backend.hcl
  backend "gcs" {
    prefix = "environments/prod"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region

  default_labels = {
    app         = "xploremore"
    environment = "prod"
    managed_by  = "terraform"
  }
}
