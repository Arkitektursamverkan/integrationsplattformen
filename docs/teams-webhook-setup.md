# Microsoft Teams Webhook Setup for Alert Notifications

This guide explains how to set up a Microsoft Teams incoming webhook so that the Integration Platform can send failure alerts to a Teams channel.

## Prerequisites

- A Microsoft Teams channel where you want to receive alerts
- Permission to add connectors/apps to the channel

---

## Step 1: Create an Incoming Webhook in Teams

### Option A: Workflows (New method, recommended)

Microsoft is migrating from Office 365 connectors to Workflows. Use this method for new setups.

1. Open **Microsoft Teams** and go to the channel where you want alerts
2. Click the **+** (Add a tab) button, or go to the channel's **...** menu
3. Select **Workflows** (or go to **Power Automate** > **Create** > **Instant cloud flow**)
4. Search for the template: **"Post to a channel when a webhook request is received"**
5. Select the template and click **Next**
6. Choose the **Team** and **Channel** to post to
7. Click **Create flow**
8. Copy the **HTTP POST URL** that is generated — this is your webhook URL

### Option B: Incoming Webhook Connector (Classic method)

> Note: Microsoft is retiring Office 365 connectors. This method may not be available in all tenants after December 2025.

1. Open **Microsoft Teams**
2. Go to the **channel** where you want to receive alerts
3. Click the **...** (More options) next to the channel name
4. Select **Connectors** (or **Manage channel** > **Connectors**)
5. Search for **"Incoming Webhook"**
6. Click **Configure**
7. Give it a name, e.g. `Integration Platform Alerts`
8. Optionally upload an icon
9. Click **Create**
10. **Copy the webhook URL** — you will need it in the next step

---

## Step 2: Configure the Integration Platform

Add the webhook URL to your environment configuration.

### Docker Compose (recommended)

Edit `docker-compose.yml` and add the `ALERT_WEBHOOK_URL` to the `api` service:

```yaml
services:
  api:
    environment:
      ALERT_WEBHOOK_URL: "https://your-tenant.webhook.office.com/webhookb2/..."
```

### .env file

Or add it to your `.env` file:

```env
ALERT_WEBHOOK_URL=https://your-tenant.webhook.office.com/webhookb2/...
```

### Restart the API

```bash
docker compose up -d --build api
```

---

## Step 3: Verify It Works

You can test the webhook by triggering a flow that will fail, or by sending a test POST manually:

```bash
curl -X POST "https://your-webhook-url" \
  -H "Content-Type: application/json" \
  -d '{
    "event": "flow.execution.failed",
    "flow_id": "test-123",
    "trigger_type": "manual",
    "error": "This is a test alert",
    "timestamp": "2026-03-31T12:00:00Z"
  }'
```

If using Workflows, the message will appear as an Adaptive Card in your channel. If using the classic connector, it will appear as a simple JSON message.

---

## What Alerts Look Like

When a flow execution fails, the platform sends a JSON payload to your webhook:

```json
{
  "event": "flow.execution.failed",
  "flow_id": "a1b2c3d4-...",
  "trigger_type": "schedule",
  "error": "Connection refused: https://api.example.com",
  "timestamp": "2026-03-31T08:00:02.123456+00:00"
}
```

### Optional: Format with Adaptive Card (Workflows)

If you want a nicely formatted card in Teams, you can modify the Workflow to parse the JSON and display it as an Adaptive Card. In Power Automate:

1. Add a **Parse JSON** action after the webhook trigger, with the schema above
2. Add a **Post adaptive card in a chat or channel** action
3. Use this card template:

```json
{
  "type": "AdaptiveCard",
  "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
  "version": "1.4",
  "body": [
    {
      "type": "TextBlock",
      "text": "Integration Platform Alert",
      "weight": "Bolder",
      "size": "Medium",
      "color": "Attention"
    },
    {
      "type": "FactSet",
      "facts": [
        { "title": "Event", "value": "@{triggerBody()?['event']}" },
        { "title": "Flow ID", "value": "@{triggerBody()?['flow_id']}" },
        { "title": "Trigger", "value": "@{triggerBody()?['trigger_type']}" },
        { "title": "Time", "value": "@{triggerBody()?['timestamp']}" }
      ]
    },
    {
      "type": "TextBlock",
      "text": "@{triggerBody()?['error']}",
      "wrap": true,
      "color": "Attention"
    }
  ]
}
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No alerts received | Check `ALERT_WEBHOOK_URL` is set correctly. Check API logs for `alert.sent` or `alert.failed` entries |
| 401/403 errors | Ensure the webhook URL is correct and hasn't expired. Regenerate if needed |
| Alerts are delayed | The alert is sent immediately on failure. If delayed, check network/firewall between the API container and Teams |
| Want to disable alerts | Set `ALERT_WEBHOOK_URL` to empty string or remove it from the environment |
