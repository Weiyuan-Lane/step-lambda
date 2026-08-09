resource "aws_s3_bucket" "ses_email" {
  bucket = "${var.project_name}-${var.environment}-ses-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "ses_email" {
  bucket = aws_s3_bucket.ses_email.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ses_email" {
  bucket = aws_s3_bucket.ses_email.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "ses_email" {
  bucket = aws_s3_bucket.ses_email.id

  rule {
    id     = "expire-inbound"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }
  }
}

resource "aws_ses_domain_identity" "main" {
  domain = var.ses_domain
}

resource "aws_ses_domain_dkim" "main" {
  domain = aws_ses_domain_identity.main.domain
}

resource "aws_ses_receipt_rule_set" "main" {
  rule_set_name = var.ses_rule_set_name
}

resource "aws_ses_active_receipt_rule_set" "main" {
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
}

resource "aws_ses_receipt_rule" "inbound" {
  name          = "${var.project_name}-${var.environment}-inbound"
  rule_set_name = aws_ses_receipt_rule_set.main.rule_set_name
  recipients    = [var.ses_recipient]
  enabled       = true
  scan_enabled  = true

  s3_action {
    bucket_name       = aws_s3_bucket.ses_email.id
    object_key_prefix = "incoming/"
    position          = 1
  }

  depends_on = [
    aws_s3_bucket_policy.ses_email,
  ]
}

# SES stores the raw email; S3 notifies Lambda once per object (no double trigger).
resource "aws_s3_bucket_notification" "ses_email" {
  bucket = aws_s3_bucket.ses_email.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.app.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
  }

  depends_on = [aws_lambda_permission.allow_s3]
}
