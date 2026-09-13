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
  type = string
}

variable "command" {
  type    = list(string)
  default = null
}

variable "args" {
  type    = list(string)
  default = []
}

variable "schedule" {
  description = "Cron expression (UTC)."
  type        = string
}

variable "paused" {
  type    = bool
  default = false
}

variable "service_account_email" {
  type = string
}

variable "scheduler_service_account_email" {
  type = string
}

variable "task_timeout" {
  type    = string
  default = "600s"
}

variable "max_retries" {
  type    = number
  default = 1
}

variable "cpu" {
  type    = string
  default = "1"
}

variable "memory" {
  type    = string
  default = "512Mi"
}

variable "env" {
  type    = map(string)
  default = {}
}

variable "secret_env" {
  type    = map(string)
  default = {}
}

variable "labels" {
  type    = map(string)
  default = {}
}

variable "deletion_protection" {
  type    = bool
  default = true
}
