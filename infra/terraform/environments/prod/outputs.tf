output "ingestor_uri" {
  value = module.ingestor.uri
}

output "api_uri" {
  value = module.api.uri
}

output "mcp_uri" {
  value = module.mcp.uri
}

output "service_accounts" {
  value = { for k, v in google_service_account.workload : k => v.email }
}

output "text_bucket" {
  value = google_storage_bucket.text.name
}

output "event_log_table" {
  value = local.event_log_table
}
