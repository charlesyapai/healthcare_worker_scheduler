# ───── Stage 1: build the React SPA ─────
FROM node:20-alpine AS web
WORKDIR /web
RUN corepack enable
COPY ui/package.json ui/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY ui/ ./
RUN pnpm build

# ───── Stage 2: Python runtime ─────
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY scheduler/ ./scheduler/
COPY api/ ./api/

# Overwrite the Phase-0 placeholder at api/static/ with the real SPA bundle.
COPY --from=web /web/dist ./api/static

EXPOSE 7860

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
