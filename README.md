# step-lambda

AWS Lambda pipeline: **Processing Steps → Output Steps**, configured in `main.py`.

SES stores inbound mail in S3; S3 notifies the Lambda. The first processing step parses that object.

```
SES → S3 ──► SES parse ──► From filter ──► Bedrock ──► Jira / Slack
```

## Layout

```
src/step_lambda/
  main.py                 # pipeline config + Processing → Output wiring
  config.py               # dotenv + Secrets Manager (production only)
  utils/                  # shared helpers (Context, …)
  processing_steps/       # steps (SESEmail, FilterFrom, Bedrock, …)
  output_steps/           # notifiers (Jira, Slack)
terraform/                # root: providers + module wiring
  modules/step-lambda/    # SES, Lambda, Secrets Manager, IAM, S3
```

## Pipeline contract

1. **Processing steps** – run in list order; each may add keys for later stages.
2. **Output steps** – run in list order; each notifies using the final context.

SES parsing reads the Lambda `event` and injects `processing::ses_email`
(`subject`, `body`, `from`, attachments, …).
`FilterFromProcessingStep` allowlists `From` via `FILTER_FROM_EMAILS` (comma-separated); non-matches raise `StopPipeline`.
Bedrock builds a user prompt from the email body and attachment filenames,
forces a Converse tool call, and sets `processing::bedrock` (`tasks`) on the
context. Edit the tool schema in `bedrock_processing_step.py` to change the
extracted fields.

Edit order / membership via the step lists in [`src/step_lambda/main.py`](src/step_lambda/main.py)
(`PROCESSING_STEPS`, `OUTPUT_STEPS`).

## Local setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+.

```bash
uv sync
cp .env.example .env
# fill in notifier credentials as needed
```

## Deploy (Terraform)

1. Package + apply:

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# set step_lambda_ses_domain, step_lambda_ses_recipient, step_lambda_secret_values

cd terraform
terraform init
terraform apply
```

Terraform runs `scripts/build_step_lambda.sh` (via `uv`) to build `.build/step-lambda.zip`, then creates:

- Lambda (`python3.14`, handler `step_lambda.main.handler`)
- Secrets Manager secret (credentials for Jira / Slack)
- S3 bucket for inbound SES mail
- SES domain identity + receipt rule (S3 store) and S3 → Lambda notification
- IAM role with S3 read, Secrets Manager read, Bedrock invoke

2. Finish SES DNS: apply the TXT / DKIM values from `terraform output`, and point the domain MX to `inbound-smtp.<region>.amazonaws.com`.

3. Enable the Bedrock model in the AWS console for your region.

## Adding a component

1. Subclass `ProcessingStep` / `OutputStep` in the matching package.
2. Add the class to `PROCESSING_STEPS` / `OUTPUT_STEPS` in `main.py` in the desired order.
3. Document any new context keys you read or write.
