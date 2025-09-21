# GitLab Events to AWS

A serverless solution for processing GitLab webhook events and forwarding them to AWS services.

## Deploy AWS Lambda

```bash
terraform init
terraform plan
terraform apply
```

The output should be:

```txt
Outputs:

api_key_value = <sensitive>
api_url = "https://<some>.execute-api.us-west-2.amazonaws.com/<stage>/<path>"
```

## Get API Key

```bash
API_URL=$(terraform output -raw api_url)
API_KEY=$(terraform output -raw api_key_value)
```

## Test with network request

```bash
curl -X POST "$API_URL" -H "x-api-key: $API_KEY" -d '{"key":"value"}'
```

## Setup GitLab Webhook

```bash
PROJECT_ID=<PROJECT ID>

glab api \
  --hostname gitlab.com \
  projects/$PROJECT_ID/hooks \
  --method POST \
  --field url="$API_URL" \
  --field issues_events=true
```

## Add Header with API Key to Webhook

```bash
PROJECT_ID=<PROJECT ID>
HOOK_ID=<HOOK ID>

glab api \
  --hostname gitlab.com \
  projects/$PROJECT_ID/hooks/$HOOK_ID/custom_headers/x-api-key \
  --method PUT \
  --field value="$API_KEY"
```

## Trigger GitLab Webhook

```bash
PROJECT_ID=<PROJECT ID>
HOOK_ID=<HOOK ID>
TRIGGER="issues_events"

glab api \
  --hostname gitlab.com \
  projects/$PROJECT_ID/hooks/$HOOK_ID/test/$TRIGGER \
  --method POST
```

## Delete GitLab Hook

```BASH
PROJECT_ID=<SOMETHING>
HOOK_ID=<HOOK ID>

glab api \
  --hostname gitlab.com \
  projects/$PROJECT_ID/hooks/$HOOK_ID \
  --method DELETE
```
