module "step_lambda" {
  source = "./modules/step-lambda"

  project_name         = var.step_lambda_project_name
  environment          = var.step_lambda_environment
  ses_domain           = var.step_lambda_ses_domain
  ses_recipient        = var.step_lambda_ses_recipient
  ses_rule_set_name    = var.step_lambda_ses_rule_set_name
  bedrock_model_id     = var.step_lambda_bedrock_model_id
  filter_from_emails   = var.step_lambda_filter_from_emails
  slack_notify_handles = var.step_lambda_slack_notify_handles
  lambda_timeout       = var.step_lambda_lambda_timeout
  lambda_memory_mb     = var.step_lambda_lambda_memory_mb
  secret_values        = var.step_lambda_secret_values

  providers = {
    aws = aws.step_lambda_deployment
  }
}
