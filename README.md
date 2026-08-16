# step-lambda

This stack turns a mailbox you control into an intake pipeline. Incoming mail is read, tasks are extracted, and the result shows up in different output formats, such as a Jira issue or a Slack notification.

![Architecture](https://github.com/user-attachments/assets/ee0f3bda-9b40-412a-bf27-522cb059ba56)

## Installation

You need to install the following first: 
- **Python 3.14**
- [uv](https://docs.astral.sh/uv/)
- [Terraform](https://developer.hashicorp.com/terraform/install)

Separately, within AWS, you need credentials that can at least create SES, S3, Lambda, IAM, Secrets Manager, and Bedrock resources.

Run the following instructions to clone and install the dependencies
```bash
git clone git@github.com:Weiyuan-Lane/step-lambda.git
cd step-lambda
uv sync
```

Next, initialize Terraform once from the `terraform/` directory:
```bash
cd terraform
terraform init
```

That's it, setup is complete!

## Usage

Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` and replace the placeholders with your region, SES domain and recipient, From allowlist, Slack notify handles, and Jira/Slack secret values. `terraform.tfvars` is gitignored.

From `terraform/`, preview the stack, then apply it:

```bash
terraform plan
```

```bash
terraform apply
```

Before you deploy, make sure to enable the Bedrock model you plan to use in the target region by using the model at least one time in the web console. You should also set up the MX, TXT, and CNAME records in your domain registrar before sending emails via your targetted domain.

## Design

The Lambda is a short pipeline: all steps share a `Context` variable and are run sequentially. Any unexpected error exits early, while caught exceptions for expected situations (e.g. email received from unintended users) are ignored and processing is paused from there.

![Code design](https://github.com/user-attachments/assets/b06af5a1-4f47-4691-890f-11d8344454cc)

**Pipeline Overview:**

- **Processing steps**
  - Built on a common interface
  - Parse → validate → extract tasks from emails
  - Easily add, remove, or swap steps sequence

- **Output steps**
  - Also use a shared interface
  - Define where/how results go (e.g., Jira, Slack)
  - Plug in new output channels with minimal code

```
src/step_lambda/
  main.py                 handler + pipeline order
  config.py               .env locally; Secrets Manager in production
  processing_steps/       parse email → allowlist From → Bedrock extract
  output_steps/           create Jira issue → post Slack message
  utils/                  Context and pipeline errors
terraform/                root module + modules/step-lambda (SES, S3, Lambda, IAM, secrets)
scripts/build_step_lambda.sh   zip built by Terraform before deploy
```

**Benefits:**
- Clear, modular pipeline design
- Easy to extend: just implement the right interface
- Steps are single-purpose and simple to test

