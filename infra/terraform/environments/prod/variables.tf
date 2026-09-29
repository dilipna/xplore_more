variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "edge_image" {
  description = "Initial Go edge image (poller + ingestor). CI deploys subsequent digests."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "indexer_image" {
  description = "Initial indexer image. CI deploys subsequent digests."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/job"
}

variable "api_image" {
  description = "Initial API image. CI deploys subsequent digests."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "mcp_image" {
  description = "Initial MCP image. CI deploys subsequent digests."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "mcp_max_instances" {
  description = "Hard cost ceiling for the MCP server (thin, stateless -- cheap per instance)."
  type        = number
  default     = 3
}

variable "api_min_instances" {
  description = "0 scales to zero (free tier). Set 1 during demos to avoid cold starts (~$0.5/day)."
  type        = number
  default     = 0
}

variable "web_image" {
  description = "Initial website image. CI deploys subsequent digests."
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
}

variable "web_min_instances" {
  description = "0 scales to zero. Set 1 during demos."
  type        = number
  default     = 0
}

variable "web_max_instances" {
  type    = number
  default = 3
}

variable "repo_url" {
  description = "Public source repository linked from the website."
  type        = string
  default     = "https://github.com/dilipna/xplore_more"
}

variable "api_max_instances" {
  description = "Hard cost ceiling for the public API."
  type        = number
  default     = 5
}

variable "api_anon_rate_per_minute" {
  description = "Unauthenticated per-IP rate limit (search/feed; problems can require a key)."
  type        = number
  default     = 30
}

variable "poller_schedule" {
  description = "Every 15 minutes: ~96 state writes/day stays inside the Cloud Storage free tier."
  type        = string
  default     = "*/15 * * * *"
}

variable "poller_problems_schedule" {
  description = "Discussion sources (Ask HN, HN comments, GitHub issues, Lobsters, Stack Exchange). Every 30 minutes: wider maturity windows than tech news, so less frequent polling still catches engagement."
  type        = string
  default     = "*/30 * * * *"
}

variable "indexer_schedule" {
  description = "Every 20 minutes: micro-batches keep serverless Postgres compute-hours inside its free tier (ADR-0006)."
  type        = string
  default     = "5-59/20 * * * *"
}

variable "text_retention_days" {
  description = "Extracted full text is kept for re-processing, then deleted."
  type        = number
  default     = 30
}

variable "event_log_retention_days" {
  type    = number
  default = 180
}
