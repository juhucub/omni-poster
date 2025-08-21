# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# system deps (psycopg binary ok; add build tools when compile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates tini && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt requirements.txt
RUN pip install -r requirements.txt

COPY backend/app ./app

# default command is uvicorn (overridden in compose for worker/beat)
ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
