# Slack Interactivity -> GitHub Actions

Frontier Scout uses Slack buttons and slash commands as the human interface, but
keeps heavy work out of Lambda. Lambda verifies Slack signatures, returns a fast
ephemeral response, and dispatches a GitHub Actions workflow for longer jobs.

## Required GitHub Setup

Create a fine-grained GitHub token for the repository:

- **Actions:** read/write
- **Contents:** read/write

Set these Lambda environment variables:

- `GH_REPO`: `owner/repo`
- `GH_BRANCH`: usually `main`
- `GH_TOKEN`: the fine-grained token above

GitHub Actions itself uses the built-in `GITHUB_TOKEN` for scheduled runs and
artifact commits.

## Slack App Setup

Configure the Slack app with:

- Interactivity URL: Lambda Function URL
- Slash commands: `/radar`, `/recall`
- Event subscriptions: `reaction_added`, `reaction_removed`, `message.channels`
- Bot scopes: `commands`, `chat:write`, `chat:write.customize`,
  `reactions:write`, `reactions:read`, `channels:history`

Reinstall the Slack app after changing scopes.

## Workflows Triggered From Slack

| Slack action | GitHub workflow |
|---|---|
| `Lab` button | `.github/workflows/lab-from-slack.yml` |
| `Evaluate` button | `.github/workflows/evaluate-from-slack.yml` |
| `Mark evaluated` overflow item | `.github/workflows/mark-seen-from-slack.yml` |
| `Snooze 30d` overflow item | `.github/workflows/snooze-from-slack.yml` |

## Verification

1. Deploy the Lambda.
2. Run `python scripts/preflight.py --skip-aws --skip-lambda` locally.
3. In Slack, run `/radar mem0`.
4. Click `Evaluate` on a verdict card.
5. Confirm a GitHub Actions run starts and replies in the same Slack thread.
