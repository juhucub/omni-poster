# omniposter / unified social media uploader

omniposter is a full-stack application for automating the ingestion, processing, scheduling, and publishing of content to multiple social media platforms (YouTube, TikTok, Instagram, Reddit).
It Includes:

-**Backend**: FastAPI + Celery + Redis + PostgreSQL
-**Frontend**: React + TypeScript + TailwindCSS
-**Workers**: Distributed crwaling and video processing pipelines w/ quota aware API clients
-**Scheduling**: Celery Beat for tiered periodic media crawls
To create the VM i used venv module that comes with Python

## Features
- **Multi-platform account linking** (OAuth for YouTube, TikTok, Instagram, Reddit)
- **Video uploads** with MIME & size validation
- **Video generation** (MoviePy integration planned)
- **Tiered creator crawling** with Redis-based Etag caching & rate limiting
- **Scheduling** for periodic ingestion
- **Secure Auth** with JWT in HTTP-only cookies, CSRF token handling, and password hashing, (more to be implemented)
- **Monitoring-ready** (will soon integrate with Sentry, Prometheus, or Grafana)

## Development Setup

2 Ways to run OmniPoster:

-**With Python virtualenv + Node locally**
-**Using Docker Compose (<3 <3)**

### 1. Local Development (Backend)

#### Activating the VM - Do this every time you start a new terminal session to work on project
    python3 -m venv .venv (ONLY ONCE)
    source .venv/bin/activate

##### Checking if VM active
which python

/home/user/code/awesome-project/.venv/bin/python - WORKING!

# TIP
everytime you install a new package in the environment, activate the environment again. 
Ensures using CLI program installed by that package uses the one from VM, not globally. 

# Upgrade PIP - not using uv might transition tho
python -m pip install --upgrade pip

# Add gitignore
echo "*" > .venv/.gitignore

# Install packages directly
if youre in a hurry and dont want to use a file to declare your package requirements, install directly

pip install "fastapi[standard]"

# TIP

Its a very good idea to put the packages and versions your program needs in a file (requirements.txt or pyproject.toml)


# Install from requirements.txt in backend
if you have one you can use it to install packages
pip install -r backend/requirements.txt

# deactivate VM
 deactivate

#COnfigure editor

# start the live server

[LOCAL] fastapi dev main.py

(Backend API Docker Compose) cd backend
uvicorn app.main:app --reload --port 8000

# Local Development (Frontend)
**Install Dependencies**
    cd frontend
    npm install
**Start dev Server**
    npm start
    #Frontend runs at http://localhost:3000 and hotreloads on changes
**Build for protection**
    npm run build

# Full stack with Docker Compose <3 <3
    **PREREQS**
        - Docker
        - Docker Compose
        - .env.dev file in project root with development settings

    **Start all Services**
    cd deploy/compose
    docker compose up --build

    **Services:**

        api (FastAPI @ http://localhost:8000, docs at /docs)

        worker (Celery worker; queue crawl)

        beat (Celery Beat scheduler)

        redis (broker/result + caches) – localhost:6379

        postgres (database) – localhost:5432


    **follow logs for a specific service**
    docker compose logs -f api
    docker compose logs -f worker
    docker compose logs -f beat

    **rebuild after code changes**
    docker compose build

    **Stop Services**
    docker compose down
