variable "project_id" {
  type = string
}

variable "name" {
  description = "Topic name, e.g. article-discovered."
  type        = string
}

variable "consumer" {
  description = "Consumer name; the subscription is <name>-<consumer>."
  type        = string
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "topic_retention" {
  description = "Topic-level retention enabling seek-based replay."
  type        = string
  default     = "604800s"
}

variable "subscription_retention" {
  type    = string
  default = "604800s"
}

variable "ack_deadline_seconds" {
  description = "Must exceed the consumer's worst-case processing time, or messages are redelivered mid-flight."
  type        = number
  default     = 60
}

variable "min_backoff" {
  type    = string
  default = "10s"
}

variable "max_backoff" {
  type    = string
  default = "600s"
}

variable "max_delivery_attempts" {
  type    = number
  default = 5

  validation {
    condition     = var.max_delivery_attempts >= 5 && var.max_delivery_attempts <= 100
    error_message = "Pub/Sub requires max_delivery_attempts between 5 and 100."
  }
}

variable "push_endpoint" {
  description = "HTTPS endpoint for push delivery; null creates a pull subscription."
  type        = string
  default     = null
}

variable "push_service_account_email" {
  description = "Identity Pub/Sub uses to sign OIDC tokens for push requests."
  type        = string
  default     = null
}

variable "push_audience" {
  type    = string
  default = null
}

variable "publisher_members" {
  type    = list(string)
  default = []
}

variable "subscriber_members" {
  description = "Members allowed to pull (pull subscriptions only)."
  type        = list(string)
  default     = []
}

variable "bigquery_table" {
  description = "project.dataset.table for an event-log BigQuery subscription, or null."
  type        = string
  default     = null
}
