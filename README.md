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

## Setup GitLab Hooks

```bash
glab api projects/:id/hooks --method POST \
  --field url="$API_URL" \
  --field issues_events=true \
  --header "x-api-key: $API_KEY"
```

Then trigger an `issue_event` from the GitLab UI and check the output on Cloud Watch
