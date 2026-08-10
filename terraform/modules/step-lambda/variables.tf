variable "project_name" {
  description = "Name prefix for resources"
  type        = string
  default     = "step-lambda"
}

variable "environment" {
  description = "Deployment environment label (use \"production\" to enable Secrets Manager loading)"
  type        = string
  default     = "production"
}

variable "ses_domain" {
  description = "Domain identity to verify for inbound SES (must be a domain you control)"
  type        = string
}

variable "ses_recipient" {
  description = "Recipient address (or domain) that triggers the receipt rule"
  type        = string
}

variable "ses_rule_set_name" {
  description = "SES receipt rule set name (must be active in the account/region)"
  type        = string
  default     = "step-lambda-rules"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID used by the processing step"
  type        = string
  default     = "anthropic.claude-3-haiku-20240307-v1:0"
}

variable "filter_from_emails" {
  description = "Comma-separated From allowlist for FilterFromProcessingStep (empty = allow all)"
  type        = string
  default     = ""
}

variable "slack_notify_handles" {
  description = "Comma-separated Slack member/usergroup IDs or @handles to notify in Slack notifications"
  type        = string
  default     = ""
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 60
}

variable "lambda_memory_mb" {
  description = "Lambda memory in MB"
  type        = number
  default     = 512
}

variable "secret_values" {
  description = <<-EOT
    Initial JSON secret payload (sensitive). Keys are loaded into the Lambda
    environment at runtime via Secrets Manager. Typical keys:
    JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY,
    JIRA_ASSIGNEE_ACCOUNT_ID, SLACK_BOT_TOKEN, SLACK_CHANNEL
  EOT
  type        = map(string)
  sensitive   = true
  default     = {}
}
