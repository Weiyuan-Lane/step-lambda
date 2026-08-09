locals {
  package_dir    = "${path.module}/../.build/lambda"
  package_zip    = "${path.module}/../.build/step-lambda.zip"
  source_hash    = filesha256("${path.module}/../uv.lock")
  project_root   = abspath("${path.module}/..")
}

# Build a Lambda-compatible zip with uv (dependencies + src).
resource "null_resource" "lambda_package" {
  triggers = {
    uv_lock     = local.source_hash
    pyproject   = filesha256("${path.module}/../pyproject.toml")
    source_tree = sha256(join("", [for f in fileset("${path.module}/../src", "**/*.py") : filesha256("${path.module}/../src/${f}")]))
  }

  provisioner "local-exec" {
    working_dir = local.project_root
    command     = "bash scripts/build_step_lambda.sh"
  }
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}"
  retention_in_days = 14
}

resource "aws_lambda_function" "app" {
  function_name = "${var.project_name}-${var.environment}"
  role          = aws_iam_role.lambda.arn
  handler       = "step_lambda.main.handler"
  runtime       = "python3.14"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_mb
  architectures = ["x86_64"]

  filename         = local.package_zip
  source_code_hash = null_resource.lambda_package.triggers.source_tree

  environment {
    variables = {
      ENVIRONMENT         = var.environment
      SECRETS_MANAGER_ARN = aws_secretsmanager_secret.app.arn
      BEDROCK_MODEL_ID    = var.bedrock_model_id
      BEDROCK_CONTEXT_KEY = "main"
      LOG_LEVEL           = "INFO"
    }
  }

  depends_on = [
    null_resource.lambda_package,
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda_app,
  ]
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id   = "AllowExecutionFromS3"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.app.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.ses_email.arn
  source_account = data.aws_caller_identity.current.account_id
}
