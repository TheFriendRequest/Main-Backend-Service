# Pub/Sub Email Notifications in Composite Service

## Overview

The Composite Service acts as a **Pub/Sub subscriber** that listens to events and sends email notifications.

## Architecture

```
Event Service → Publishes → Pub/Sub Topic: event-created
                                      ↓
                            Subscription: event-notification-sub
                                      ↓
                            Composite Service Subscriber
                                      ↓
                            Lookup email by user_id
                                      ↓
                            Send email notification

User Service → Publishes → Pub/Sub Topic: user-created
                                      ↓
                            Subscription: user-welcome-sub
                                      ↓
                            Composite Service Subscriber
                                      ↓
                            Send welcome email
```

## Setup

### 1. GCP Pub/Sub Setup

```bash
# Create topics
gcloud pubsub topics create event-created
gcloud pubsub topics create user-created

# Create subscriptions
gcloud pubsub subscriptions create event-notification-sub \
  --topic=event-created

gcloud pubsub subscriptions create user-welcome-sub \
  --topic=user-created
```

### 2. Environment Variables

Add to `Main-Backend-Service/.env`:

```env
# GCP Configuration
GCP_PROJECT_ID=your-gcp-project-id
# OR
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Pub/Sub Topics (optional, defaults shown)
PUBSUB_EVENT_CREATED_TOPIC=event-created
PUBSUB_USER_CREATED_TOPIC=user-created

# Pub/Sub Subscriptions (optional, defaults shown)
PUBSUB_EVENT_NOTIFICATION_SUB=event-notification-sub
PUBSUB_USER_WELCOME_SUB=user-welcome-sub

# SMTP Configuration for Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password
SMTP_FROM=your-email@gmail.com
```

### 3. GCP Service Account

The Composite Service needs Pub/Sub subscriber permissions:

```bash
# Grant subscriber role to service account
gcloud projects add-iam-policy-binding your-project-id \
  --member="serviceAccount:your-service-account@project.iam.gserviceaccount.com" \
  --role="roles/pubsub.subscriber"
```

Set credentials:
```bash
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

## How It Works

### Event Created Notification

1. **Event Service** publishes to `event-created` topic:
   ```json
   {
     "event_id": 123,
     "user_id": 42,
     "event_data": {...}
   }
   ```

2. **Composite Service Subscriber** receives message

3. **Looks up user email**:
   - Calls User Service: `GET /users/42`
   - Gets email, first_name, etc.

4. **Sends email** to user

### User Created Notification

1. **User Service** publishes to `user-created` topic:
   ```json
   {
     "user_id": 42,
     "email": "user@example.com",
     "first_name": "John",
     "role": "user"
   }
   ```

2. **Composite Service Subscriber** receives message

3. **Sends welcome email** directly (email already in message)

## Subscriber Threads

Subscribers run in background threads (started automatically):

- **Event Subscriber Thread**: Listens to `event-notification-sub`
- **User Subscriber Thread**: Listens to `user-welcome-sub`

Both run as daemon threads, so they stop when the main process stops.

## Testing

### Test Email Sending

Set SMTP credentials and test:

```python
from email_service import send_email

send_email(
    to="test@example.com",
    subject="Test Email",
    body="This is a test email from Composite Service"
)
```

### Test Pub/Sub Subscriber

1. Start Composite Service
2. Publish a test message to the topic
3. Check logs for email sending confirmation

## Email Templates

Currently using plain text emails. You can enhance with HTML:

```python
html_body = """
<html>
<body>
<h1>Event Created!</h1>
<p>Your event has been created successfully.</p>
</body>
</html>
"""
send_html_email(to, subject, html_body)
```

## Troubleshooting

### "GCP_PROJECT_ID not set"
- Set `GCP_PROJECT_ID` or `GOOGLE_CLOUD_PROJECT` environment variable

### "SMTP credentials not configured"
- Set `SMTP_USER` and `SMTP_PASS` environment variables
- For Gmail, use an App Password (not regular password)

### Subscribers not starting
- Check GCP credentials are set correctly
- Verify subscriptions exist in GCP
- Check service account has subscriber permissions

### Emails not sending
- Check SMTP credentials
- Verify SMTP_HOST and SMTP_PORT are correct
- Check firewall/network allows SMTP connections

