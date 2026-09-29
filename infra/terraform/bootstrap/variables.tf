variable "project_id" {
  description = "GCP project that hosts XploreMore."
  type        = string
}

variable "region" {
  description = "Primary region. us-central1 qualifies for Cloud Run and Cloud Storage free tiers."
  type        = string
  default     = "us-central1"
}

variable "github_repository" {
  description = "owner/name of the only GitHub repository allowed to exchange OIDC tokens."
  type        = string
  default     = "dilipna/xplore_more"

  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "github_repository must look like owner/name."
  }
}

variable "github_repository_id" {
  description = "Immutable numeric GitHub repository id (gh api repos/OWNER/NAME --jq .id). Strongly recommended."
  type        = string
  default     = ""

  validation {
    condition     = var.github_repository_id == "" || can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "github_repository_id must be numeric."
  }
}

variable "deploy_ref" {
  description = "Git ref allowed to deploy (apply). Pull requests can only plan."
  type        = string
  default     = "refs/heads/main"
}

variable "billing_account_id" {
  description = "Billing account for budget alerts. Leave empty to skip budget creation."
  type        = string
  default     = ""
}

variable "monthly_budget_usd" {
  description = "Budget amount; alerts fire at 1%, 10%, 50%, 100% so a free-tier breach is noticed within hours."
  type        = number
  default     = 25
}
