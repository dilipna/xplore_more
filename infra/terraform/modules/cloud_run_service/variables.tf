variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "name" {
  type = string
}

variable "image" {
  description = "Initial image. Later deploys are done by CI (see lifecycle.ignore_changes)."
  type        = string
}

variable "service_account_email" {
  type = string
}

variable "ingress" {
  description = "INGRESS_TRAFFIC_ALL for public APIs; INGRESS_TRAFFIC_INTERNAL_ONLY for push targets."
  type        = string
  default     = "INGRESS_TRAFFIC_INTERNAL_ONLY"

  validation {
    condition     = contains(["INGRESS_TRAFFIC_ALL", "INGRESS_TRAFFIC_INTERNAL_ONLY", "INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER"], var.ingress)
    error_message = "Unsupported ingress setting."
  }
}

variable "min_instances" {
  type    = number
  default = 0
}

variable "max_instances" {
  type    = number
  default = 3
}

variable "concurrency" {
  type    = number
  default = 40
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "request_timeout" {
  type    = string
  default = "60s"
}

variable "health_path" {
  type    = string
  default = "/healthz"
}

variable "env" {
  type    = map(string)
  default = {}
}

variable "secret_env" {
  description = "Environment variable name -> Secret Manager secret id."
  type        = map(string)
  default     = {}
}

variable "invoker_members" {
  description = "Principals allowed to invoke. Use [\"allUsers\"] only for the public API."
  type        = list(string)
  default     = []
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "deletion_protection" {
  type    = bool
  default = true
}
