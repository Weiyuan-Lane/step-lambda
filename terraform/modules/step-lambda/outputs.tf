output "lambda_function_name" {
  value = aws_lambda_function.app.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.app.arn
}

output "ses_email_bucket" {
  value = aws_s3_bucket.ses_email.id
}

output "secrets_manager_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "ses_domain_verification_token" {
  description = "Add as a TXT record on _amazonses.<domain>"
  value       = aws_ses_domain_identity.main.verification_token
}

output "ses_dkim_tokens" {
  description = "Add as CNAME records for DKIM"
  value       = aws_ses_domain_dkim.main.dkim_tokens
}

output "ses_rule_set_name" {
  value = aws_ses_receipt_rule_set.main.rule_set_name
}
