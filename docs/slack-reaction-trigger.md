# Slack 🧪 reaction → Bitbucket Pipeline

Wires a `🧪` reaction in `#ai-telemetry` to the `lab-from-slack` custom pipeline.
No webhook server. Slack Workflow Builder POSTs directly to Bitbucket's REST API.

## One-time setup

### 1. Bitbucket: create an App Password

1. Profile → Personal settings → App passwords → **Create app password**
2. Label: `ai-telemetry slack trigger`
3. Permissions: **Pipelines: Read + Write**
4. Save the password — you can't view it again.

### 2. Slack: build the workflow

1. Slack → Tools → Workflow Builder → New workflow → **From scratch**
2. Trigger: **Emoji reaction added** → emoji `🧪`, channel `#ai-telemetry`
3. Step: **Send a web request** (built-in)
   - **URL**:
     ```
     https://api.bitbucket.org/2.0/repositories/YOUR_WORKSPACE/ai-telemetry/pipelines/
     ```
   - **Method**: `POST`
   - **Authentication**: Basic Auth — username = your Bitbucket username, password = app password from step 1
   - **Headers**: `Content-Type: application/json`
   - **Body** (JSON):
     ```json
     {
       "target": {
         "ref_type": "branch",
         "type": "pipeline_ref_target",
         "ref_name": "main",
         "selector": {"type": "custom", "pattern": "lab-from-slack"}
       },
       "variables": [
         {"key": "TOOL", "value": "{{message_text}}"},
         {"key": "URL",  "value": "{{message_link}}"},
         {"key": "USER", "value": "{{user_name}}"}
       ]
     }
     ```
4. Publish the workflow.

### 3. Test

1. Post any message in `#ai-telemetry`
2. React 🧪 on it
3. Check Bitbucket → Pipelines — a `lab-from-slack` run should appear within 30s
4. The pipeline will commit `.scratch/labs/<date>-<tool>.md` back to `main`

## What's in the payload

The `TOOL` variable will be the literal message text from Slack — when the Pulse
or Scout post is structured as `*<TOOL_NAME>* — verdict...`, the `<TOOL_NAME>`
appears in the text after the markdown brackets are stripped. If you want
cleaner extraction, parse `TOOL` from the URL via `scripts/lab_from_slack.py`
(extend as needed).

## Security note (SOC2)

The Bitbucket App Password lives only in Slack Workflow Builder's encrypted
storage. It is scoped to Pipelines read/write only — cannot read code, cannot
push commits outside what `lab-from-slack` does, cannot read other repos in
the workspace. Rotate annually alongside the other AI Telemetry secrets.
