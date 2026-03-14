# Webhook Intake Setup

The harness exposes receive-only webhook endpoints for GitHub, Slack, Jira, and Confluence. In this phase the endpoints only verify, normalize, log, and acknowledge deliveries. They do not create work items.

## Shared prerequisites

- Set `WEBHOOK_BASE_URL` in `.env` to the externally reachable base URL for this server.
- Keep secrets in `.env`. This phase does not store webhook secrets through the UI.
- Register webhooks manually in each external system.

## GitHub Enterprise Cloud

- Callback URL: `WEBHOOK_BASE_URL/webhooks/github`
- Secret env key: `GITHUB_WEBHOOK_SECRET`
- Verification: `X-Hub-Signature-256` HMAC SHA-256 when a secret is configured
- Recommended events:
  - `pull_request`
  - `pull_request_review`
  - `pull_request_review_comment`
  - `issues`
  - `issue_comment`

## Slack Enterprise Grid

- Callback URL: `WEBHOOK_BASE_URL/webhooks/slack/events`
- Secret env key: `SLACK_SIGNING_SECRET`
- Verification: `X-Slack-Signature` with `X-Slack-Request-Timestamp`
- Recommended events:
  - `app_mention`
  - `message.im`
  - `message.channels`
- Notes:
  - Slack will send a `url_verification` challenge before live event callbacks begin.

## Jira Self-Hosted Enterprise

- Callback URL: `WEBHOOK_BASE_URL/webhooks/jira`
- Optional secret env key: `JIRA_WEBHOOK_SHARED_SECRET`
- Verification: optional shared secret via `X-Webhook-Shared-Secret`
- Recommended events:
  - `jira:issue_created`
  - `jira:issue_updated`
  - `comment_created`
  - `issue_generic`

## Confluence Self-Hosted Enterprise

- Callback URL: `WEBHOOK_BASE_URL/webhooks/confluence`
- Optional secret env key: `CONFLUENCE_WEBHOOK_SECRET`
- Verification: `X-Hub-Signature` HMAC SHA-256 when a secret is configured
- Recommended events:
  - `page_created`
  - `page_updated`
  - `comment_created`
