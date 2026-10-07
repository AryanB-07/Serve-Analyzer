# Two images from one file:
#   docker build --target app -t serve-analyzer-app .   # API and worker (different commands)
#   docker build --target web -t serve-analyzer-web .   # Caddy: HTTPS, the built frontend, /api proxy
# deploy/docker-compose.yml builds and runs both.

# --- frontend build -------------------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- API and worker -------------------------------------------------------------------
FROM python:3.11-slim AS app
# OpenCV and MediaPipe need these shared libraries even without a display.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libegl1 libgles2 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /usr/local/bin/uv
# A static ffmpeg (with libx264) re-encodes result videos to H.264, which OpenCV's Linux wheels
# can't write (see video.make_browser_playable). Debian's ffmpeg package would add about 2 GB.
COPY --from=mwader/static-ffmpeg:7.1.1 /ffmpeg /usr/local/bin/ffmpeg

RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
# The cache mount keeps uv's download cache (about 600 MB) out of the image.
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra api --no-install-project
COPY serve_analyzer/ serve_analyzer/
COPY serve_api/ serve_api/
COPY alembic.ini ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --extra api

USER app
# Bake the pose model into the image so workers never download it at startup.
RUN python -c "from serve_analyzer.config import AnalysisConfig as C; \
from serve_analyzer.pose import ensure_model; c = C(); ensure_model(c.model_variant, c.model_dir)"

# Video decoding runs in many threads, and glibc gives each its own memory arena that it
# rarely returns. Two arenas cut the worker's memory after a 1080p job from about 520 to 380 MB.
ENV SERVE_API_ENV=production SERVE_API_DATA_DIR=/data MALLOC_ARENA_MAX=2
EXPOSE 8000
# --proxy-headers: trust Caddy's X-Forwarded-For so rate limits see the real client IP.
# The API is only reachable from Caddy on the compose network.
# --no-access-log: don't keep a log of every request's IP address (see the Privacy Policy);
# errors and the worker's job log are still written.
CMD ["sh", "-c", "exec uvicorn serve_api.app:create_app --factory --host 0.0.0.0 --port 8000 \
--proxy-headers --forwarded-allow-ips='*' --no-access-log --workers ${API_PROCESSES:-2}"]

# --- web: Caddy with the built frontend ------------------------------------------------
FROM caddy:2 AS web
COPY deploy/Caddyfile /etc/caddy/Caddyfile
COPY --from=frontend /src/frontend/dist /srv
