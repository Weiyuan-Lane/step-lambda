# Aliased provider for the step-lambda module. Configure region/tags here so the
# module can be dropped into another root (e.g. a shared devops repo) without
# changing that root's default provider settings.
provider "aws" {
  alias  = "step_lambda_deployment"
  region = var.step_lambda_aws_region

  default_tags {
    tags = {
      Project     = var.step_lambda_project_name
      ManagedBy   = "terraform"
      Environment = var.step_lambda_environment
    }
  }
}

# Defaults - which could already exist in your root module.
provider "aws" {
  region = "ap-southeast-1"
}
