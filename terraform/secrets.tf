resource "aws_secretsmanager_secret" "app" {
  name                    = "${var.project_name}/${var.environment}/app"
  description             = "API credentials for step-lambda notifiers (Jira, Slack)"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode(
    merge(
      {
        # Placeholders – override via terraform.tfvars / -var secret_values
        JIRA_BASE_URL             = ""
        JIRA_EMAIL                = ""
        JIRA_API_TOKEN            = ""
        JIRA_PROJECT_KEY          = ""
        JIRA_ASSIGNEE_ACCOUNT_ID  = ""
        SLACK_BOT_TOKEN           = ""
        SLACK_CHANNEL             = ""
      },
      var.secret_values
    )
  )
}
