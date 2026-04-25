# Omni-poster

Omni-poster is a YouTube Shorts MVP with one honest vertical slice:

`project creation -> script editing -> preview generation -> metadata -> publish/schedule -> post history`

## Stack
- Backend: FastAPI + SQLAlchemy + Alembic
- Jobs: Celery + Redis
- Database: PostgreSQL
- Frontend: React + TypeScript

## Local Docker Run
1. Create a `.env.dev` in the repo root from `.env.example`.
2. Start the stack:

```bash
docker compose -f deploy/compose/docker-compose.yml up --build
```

Services:
- API: `http://localhost:8000`
- Health: `http://localhost:8000/health`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`
- Voice preview worker: processes OpenVoice previews on a dedicated single-concurrency queue

The API container runs `alembic upgrade head` before starting Uvicorn.

## OpenVoice Runtime Notes
- OpenVoice previews now run on the dedicated `voice_worker` service instead of inside the FastAPI process.
- `espeak` previews still run synchronously in the API for fast local feedback.
- If Docker Desktop is memory-constrained, the `voice_worker` may still hit OOM during OpenVoice loads on CPU. Increase Docker memory if you see worker exits with code `137`.

## Required YouTube Settings
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REDIRECT_URI`
- `OAUTH_TOKEN_ENCRYPTION_KEY`

`YOUTUBE_REDIRECT_URI` should point to the backend callback route:

```text
http://localhost:8000/social-accounts/youtube/callback
```

## Test Scope
The backend test suite covers:
- auth flow
- project/script/assets flow
- generation job lifecycle
- YouTube OAuth link + refresh
- publish job lifecycle
- scheduled dispatch
- end-to-end happy path
