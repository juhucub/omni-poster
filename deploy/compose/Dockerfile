# syntax=docker/dockerfile:1
FROM python:3.10-slim-bullseye

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    NLTK_DATA=/usr/local/share/nltk_data \
    OPENVOICE_REPO_DIR=/opt/openvoice/repo \
    OPENVOICE_CHECKPOINTS_DIR=/opt/openvoice/checkpoints_v2

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    tini \
    espeak-ng \
    ffmpeg \
    git \
    libsndfile1 \
    pkg-config \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt requirements.txt
RUN pip install -r requirements.txt

RUN pip install --index-url https://download.pytorch.org/whl/cpu torch torchaudio
RUN pip install git+https://github.com/myshell-ai/MeloTTS.git
RUN python - <<'PY'
import torch

# Pre-trust and cache Silero VAD so runtime VAD calls stay non-interactive in Docker.
torch.hub.load(
    repo_or_dir="snakers4/silero-vad",
    model="silero_vad",
    trust_repo=True,
    skip_validation=True,
    onnx=False,
)
PY
# Required for Melo/OpenVoice English g2p_en synthesis inside the container.
RUN python - <<'PY'
import os

import nltk

download_dir = os.environ["NLTK_DATA"]
os.makedirs(download_dir, exist_ok=True)
for resource in (
    "averaged_perceptron_tagger_eng",
    "averaged_perceptron_tagger",
    "cmudict",
):
    nltk.download(resource, download_dir=download_dir)
PY
RUN python -m unidic download

# make sure the non-isolated build has the right toolchain already installed
RUN pip install --upgrade "Cython<3" wheel "setuptools>=77"

COPY vendor/OpenVoice /opt/openvoice/repo
RUN pip install --no-build-isolation -e /opt/openvoice/repo

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
