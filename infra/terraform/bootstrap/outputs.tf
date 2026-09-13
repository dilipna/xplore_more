output "workload_identity_provider" {
  description = "Set as GitHub variable GCP_WORKLOAD_IDENTITY_PROVIDER."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "deployer_service_account" {
  description = "Set as GitHub variable GCP_DEPLOYER_SA."
  value       = google_service_account.deployer.email
}

output "planner_service_account" {
  description = "Set as GitHub variable GCP_PLANNER_SA."
  value       = google_service_account.planner.email
}

output "state_bucket" {
  value = google_storage_bucket.tfstate.name
}

output "registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}
