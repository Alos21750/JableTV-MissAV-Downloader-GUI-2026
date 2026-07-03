# JableTV · MissAV · SupJav headless downloader — for Docker / NAS (issue #28).
# Runs docker_cli.py (no GUI): pass URL(s), video is downloaded to /downloads.
FROM python:3.12-slim

# ffmpeg = TS->MP4 remux; ca-certificates = TLS. Slim + cleaned apt lists.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# deps first for layer caching
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY . .

ENV DOWNLOAD_DIR=/downloads \
    PYTHONUNBUFFERED=1
VOLUME ["/downloads"]

# URL(s) are passed as CMD args (or via URLS / URLS_FILE env)
ENTRYPOINT ["python", "-u", "docker_cli.py"]
