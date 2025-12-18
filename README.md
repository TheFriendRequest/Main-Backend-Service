# Composite Service

Orchestrator service that coordinates atomic microservices, handles Pub/Sub subscriptions, and provides unified API endpoints.

## 📋 Overview

The Composite Service acts as the central orchestrator for the microservices architecture:
- Routes requests to appropriate atomic services (Users, Events, Feed)
- Handles Pub/Sub message consumption for email notifications
- Provides composite endpoints (e.g., user feed with events and posts)
- Manages GraphQL API
- Coordinates cross-service operations

## 🏗️ Architecture

```
API Gateway → Composite Service → Atomic Services
                ↓
            Pub/Sub Subscriptions
                ↓
            Email Notifications
```

- **Port**: 8004
- **Authentication**: Trusts `x-firebase-uid` header from API Gateway
- **Pub/Sub**: Subscribes to `event-created` and `user-created` topics

## 🚀 Setup

### Prerequisites

- Python 3.9+
- Firebase service account key
- Google Cloud Pub/Sub (for email notifications)
- SMTP server credentials (for email sending)

### Installation

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   Create a `.env` file:
   ```env
   # Service URLs
   USERS_SERVICE_URL=http://localhost:8001
   EVENTS_SERVICE_URL=http://localhost:8002
   FEED_SERVICE_URL=http://localhost:8003
   
   # GCP Configuration
   GCP_PROJECT_ID=your-project-id
   GOOGLE_CLOUD_PROJECT=your-project-id
   
   # Pub/Sub Topics
   PUBSUB_EVENT_CREATED_TOPIC=event-created
   PUBSUB_USER_CREATED_TOPIC=user-created
   
   # Pub/Sub Subscriptions
   PUBSUB_EVENT_NOTIFICATION_SUB=event-notification-sub
   PUBSUB_USER_WELCOME_SUB=user-welcome-sub
   
   # SMTP Configuration
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=your-email@gmail.com
   SMTP_PASS=your-app-password
   SMTP_FROM=your-email@gmail.com
   
   # Firebase
   FIREBASE_SERVICE_ACCOUNT_PATH=./serviceAccountKey.json
   ```

3. **Add Firebase service account key**
   - Download from Firebase Console
   - Place as `serviceAccountKey.json` in service directory

4. **Set up Pub/Sub topics and subscriptions**
   See [README_PUBSUB.md](./README_PUBSUB.md) for detailed instructions.

5. **Run the service**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8004
   ```

   The service will automatically start Pub/Sub subscribers in background threads.

## 🔧 Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|---------|
| `USERS_SERVICE_URL` | Users Service URL | `http://localhost:8001` | Yes |
| `EVENTS_SERVICE_URL` | Event Service URL | `http://localhost:8002` | Yes |
| `FEED_SERVICE_URL` | Feed Service URL | `http://localhost:8003` | Yes |
| `GCP_PROJECT_ID` | GCP project ID | - | Yes |
| `GOOGLE_CLOUD_PROJECT` | Same as GCP_PROJECT_ID | - | Yes |
| `PUBSUB_EVENT_CREATED_TOPIC` | Pub/Sub topic name | `event-created` | No |
| `PUBSUB_USER_CREATED_TOPIC` | Pub/Sub topic name | `user-created` | No |
| `PUBSUB_EVENT_NOTIFICATION_SUB` | Pub/Sub subscription name | `event-notification-sub` | No |
| `PUBSUB_USER_WELCOME_SUB` | Pub/Sub subscription name | `user-welcome-sub` | No |
| `SMTP_HOST` | SMTP server host | - | Yes (for emails) |
| `SMTP_PORT` | SMTP server port | `587` | No |
| `SMTP_USER` | SMTP username | - | Yes (for emails) |
| `SMTP_PASS` | SMTP password | - | Yes (for emails) |
| `SMTP_FROM` | From email address | - | Yes (for emails) |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Path to Firebase service account JSON | `./serviceAccountKey.json` | No |

## 📡 API Endpoints

### Composite Endpoints

#### `GET /api/users/me/feed`
Get personalized feed for current user (events + posts)

**Query Parameters:**
- `skip_posts`: Number of posts to skip (default: 0)
- `limit_posts`: Number of posts to return (default: 5, max: 100)
- `skip_events`: Number of events to skip (default: 0)
- `limit_events`: Number of events to return (default: 5, max: 100)

**Response:**
```json
{
  "user_id": 1,
  "events": [
    {
      "event_id": 1,
      "title": "Tech Meetup",
      "start_time": "2024-01-15T18:00:00",
      ...
    }
  ],
  "posts": [
    {
      "post_id": 1,
      "title": "My Post",
      "created_at": "2024-01-01T00:00:00",
      ...
    }
  ]
}
```

### Proxy Endpoints

The Composite Service proxies requests to atomic services:

- `/api/users/*` → Users Service
- `/api/events/*` → Event Service
- `/api/posts/*` → Feed Service
- `/api/friends/*` → Users Service (friend management)

All requests are forwarded with the `x-firebase-uid` header.

### GraphQL Endpoint

#### `POST /graphql`
GraphQL API endpoint

**Query Example:**
```graphql
query {
  users {
    user_id
    username
    email
  }
  events {
    event_id
    title
    location
  }
}
```

See [graphql_api/schema.py](./graphql_api/schema.py) for available queries and mutations.

## 📨 Pub/Sub Integration

### Subscriptions

The service subscribes to two Pub/Sub topics:

1. **`event-notification-sub`** (subscribes to `event-created` topic)
   - Triggered when a new event is created
   - Sends email notification to event creator

2. **`user-welcome-sub`** (subscribes to `user-created` topic)
   - Triggered when a new user is created
   - Sends welcome email to new user

### Message Flow

```
Event Service → Publishes to "event-created" topic
                ↓
Composite Service → Consumes message
                ↓
Email Service → Sends notification email
```

### Starting Subscribers

Subscribers start automatically when the service starts:

```python
# In main.py
start_event_subscriber()
start_user_subscriber()
```

## 📧 Email Service

The service includes email functionality for:
- Event creation notifications
- User welcome emails

**SMTP Configuration:**
- Supports Gmail, Outlook, and other SMTP servers
- Uses TLS/STARTTLS for secure connections
- Requires app-specific password for Gmail

## 🔐 Authentication

This service **does not** perform Firebase authentication directly. It:
- Receives `x-firebase-uid` header from API Gateway
- Forwards this header to atomic services
- Uses `firebase_uid` from `request.state` (set by API Gateway middleware)

## 🐳 Docker Deployment

### Build Image
```bash
docker build -t composite-service .
```

### Run Container
```bash
docker run -p 8004:8004 \
  -e USERS_SERVICE_URL=http://users-service:8001 \
  -e EVENTS_SERVICE_URL=http://event-service:8002 \
  -e FEED_SERVICE_URL=http://feed-service:8003 \
  -e GCP_PROJECT_ID=your-project-id \
  -e SMTP_HOST=smtp.gmail.com \
  -e SMTP_USER=your-email@gmail.com \
  -e SMTP_PASS=your-app-password \
  composite-service
```

## ☁️ GCP Cloud Run Deployment

The service is deployed to Cloud Run with:
- VPC Connector for accessing VM services
- Pub/Sub subscriber permissions
- Environment variables configured via deployment script
- Background threads for Pub/Sub subscribers

See [../GCP_DEPLOYMENT_GUIDE.md](../GCP_DEPLOYMENT_GUIDE.md) for details.

## 🧪 Testing

### Health Check
```bash
curl http://localhost:8004/
```

### Get User Feed
```bash
curl -H "x-firebase-uid: your-firebase-uid" \
     "http://localhost:8004/api/users/me/feed?limit_posts=10&limit_events=10"
```

### Test Pub/Sub (Local)
```bash
python debug_pubsub.py
```

### Test Email Service
```python
from email_service import send_email

send_email(
    to="test@example.com",
    subject="Test Email",
    body="This is a test email"
)
```

## 📚 API Documentation

Interactive API documentation available at:
- Swagger UI: `http://localhost:8004/docs`
- ReDoc: `http://localhost:8004/redoc`
- OpenAPI JSON: `http://localhost:8004/openapi.json`
- GraphQL Playground: `http://localhost:8004/graphql` (if enabled)

## 🔍 Error Handling

The service returns standard HTTP status codes:

- `200 OK`: Successful request
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid `x-firebase-uid` header
- `404 Not Found`: Resource not found
- `502 Bad Gateway`: Downstream service unavailable
- `500 Internal Server Error`: Server error

## 🎯 Features

- **Service Orchestration**: Routes requests to appropriate atomic services
- **Pub/Sub Integration**: Event-driven email notifications
- **Composite Endpoints**: Unified endpoints combining multiple services
- **GraphQL API**: Flexible querying of data
- **Error Handling**: Graceful handling of downstream service failures
- **Request Forwarding**: Maintains authentication headers across services

## 📝 Notes

- Pub/Sub subscribers run in background threads and persist for the service lifetime
- Email service uses synchronous SMTP connections
- Service URLs can point to Cloud Run URLs or VM private IPs
- The service acts as a reverse proxy for atomic services

## 📖 Additional Documentation

- [Pub/Sub Setup Guide](./README_PUBSUB.md) - Detailed Pub/Sub configuration
- [GraphQL Schema](./graphql_api/schema.py) - GraphQL API schema

## 🤝 Contributing

When adding new endpoints:
1. Add route to `routers/composite_router.py`
2. Use `request.state.firebase_uid` for user identification
3. Forward requests to atomic services using `forward_request()` helper
4. Add proper error handling
5. Update this README with endpoint documentation

