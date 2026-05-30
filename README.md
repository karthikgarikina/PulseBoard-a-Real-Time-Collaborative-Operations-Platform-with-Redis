# PulseBoard - Redis-Powered Collaboration Backend

## Project Overview

PulseBoard is a backend-focused collaboration platform built with FastAPI and Redis. The goal of this project is to demonstrate how Redis can be used beyond caching by acting as a primary operational data layer for real-time applications.

The system includes authentication, rate limiting, activity feeds, workspace management, presence tracking, real-time messaging, event streaming, analytics, distributed locks, job scheduling, and geospatial queries.

This project is designed for API-first testing and can be explored through Swagger UI, Postman, curl commands, WebSockets, or the included smoke test script.

---

## Objectives

- Build a production-style backend using FastAPI and Redis.
- Demonstrate multiple Redis data structures in real-world scenarios.
- Implement asynchronous background processing using workers and schedulers.
- Support real-time communication using Pub/Sub and WebSockets.
- Provide analytics and operational features commonly used in collaborative platforms.
- Deliver a fully containerized development environment using Docker Compose.

---

## System Architecture

```text
                    ┌─────────────────┐
                    │     Client      │
                    │ Swagger/Postman │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   FastAPI API   │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   Redis Pub/Sub      Redis Streams      Redis Data Store
         │                   │                   │
         ▼                   ▼                   ▼
   Subscriber          Worker Service      Sessions
                                            Presence
                                            Feeds
                                            Analytics
                                            Geo Data
                                            Locks
                                            Jobs

                             ▲
                             │
                    ┌─────────────────┐
                    │   Scheduler     │
                    └─────────────────┘
```

### Services

| Service | Responsibility |
|----------|---------------|
| API | REST APIs and WebSocket endpoints |
| Redis | Central operational datastore |
| Worker | Processes streams and background jobs |
| Scheduler | Moves scheduled jobs into processing queues |
| Subscriber | Monitors and logs Pub/Sub events |

---

## Tech Stack

- FastAPI
- Redis 7
- Docker
- Docker Compose
- WebSockets
- Redis Streams
- Redis Pub/Sub
- Python

---

# Getting Started

## 1. Clone the Repository

```bash
git clone https://github.com/karthikgarikina/PulseBoard-a-Real-Time-Collaborative-Operations-Platform-with-Redis

cd PulseBoard-a-Real-Time-Collaborative-Operations-Platform-with-Redis
```

## 2. Configure Environment

```bash
cp .env.example .env
```

Default values are already configured for local development.

---

## 3. Build and Start the Application

```bash
docker compose up --build
```

For detached mode:

```bash
docker compose up --build -d
```

Verify running containers:

```bash
docker compose ps
```

---

## 4. Access the Application

| Resource | URL |
|-----------|-----|
| API Base URL | http://localhost:8000 |
| Interactive API Docs | http://localhost:8000/docs |
| OpenAPI Schema | http://localhost:8000/openapi.json |

### First Thing To Check

After the containers start successfully, open:

```text
http://localhost:8000/docs
```

The Swagger documentation provides an easy way to test every endpoint without writing curl commands manually.

---

# Project Walkthrough

## Step 1: Create a Session

```bash
curl -X POST http://localhost:8000/auth/login \
-H "Content-Type: application/json" \
-d '{
  "email":"ada@pulseboard.local",
  "user_id":"ada",
  "name":"Ada Lovelace"
}'
```

Copy the returned session token.

---

## Step 2: Verify Authentication

```bash
curl http://localhost:8000/auth/session/<TOKEN>
```

---

## Step 3: Mark User Online

```bash
curl -X POST http://localhost:8000/presence/online \
-H "X-Session-Token: <TOKEN>"
```

---

## Step 4: Create Workspace Membership

```bash
curl -X POST \
http://localhost:8000/workspaces/incidents/members/ada \
-H "X-Session-Token: <TOKEN>"
```

View members:

```bash
curl http://localhost:8000/workspaces/incidents/members \
-H "X-Session-Token: <TOKEN>"
```

---

## Step 5: Send Real-Time Messages

```bash
curl -X POST \
http://localhost:8000/channels/demo/messages \
-H "Content-Type: application/json" \
-H "X-Session-Token: <TOKEN>" \
-d '{"content":"Deployment started"}'
```

You can also connect to:

```text
/ws/channels/{channel_id}
```

to test WebSocket communication.

---

## Step 6: Explore Analytics

Trending channels:

```bash
curl http://localhost:8000/analytics/trending \
-H "X-Session-Token: <TOKEN>"
```

Reputation leaderboard:

```bash
curl http://localhost:8000/analytics/reputation \
-H "X-Session-Token: <TOKEN>"
```

Daily active users:

```bash
curl http://localhost:8000/analytics/dau \
-H "X-Session-Token: <TOKEN>"
```

---

# Redis Features Demonstrated

| Feature | Redis Data Structure |
|----------|---------------------|
| Sessions | Strings |
| Rate Limiting | Counters |
| Activity Feed | Lists |
| Presence Tracking | Sets |
| Workspace Membership | Sets |
| User Profiles | Hashes |
| Messaging | Pub/Sub |
| Event Processing | Streams |
| Trending Analytics | Sorted Sets |
| Reputation System | Sorted Sets |
| Distributed Locks | Strings + NX/EX |
| Attendance Tracking | Bitmaps |
| DAU Tracking | HyperLogLog |
| Geo Search | GEO Index |
| Background Jobs | Lists + Sorted Sets |

---

# Running the Smoke Test

After all containers are healthy:

```powershell
.\scripts\smoke-test.ps1
```

Expected output:

```text
PASS: all PulseBoard Redis requirement smoke checks passed.
```

---

# Useful Commands

### View Logs

```bash
docker compose logs api --tail 100
docker compose logs worker --tail 100
docker compose logs scheduler --tail 100
docker compose logs subscriber --tail 100
```

### Stop Services

```bash
docker compose down
```

### Rebuild Everything

```bash
docker compose down
docker compose up --build
```

---

# Video Link

https://www.youtube.com/watch?v=YYHt6JBGbjg

# Key Learning Outcomes

This project demonstrates:

- FastAPI application design
- Redis data structures in practical systems
- Pub/Sub based communication
- Event-driven architecture
- Background job processing
- Distributed locking
- Real-time presence tracking
- API rate limiting
- Containerized deployment workflows

---