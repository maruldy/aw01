# --- Stage 1: Build frontend ---
FROM --platform=linux/amd64 reg.navercorp.com/base/ubuntu/python:3.12 AS frontend

ENV HTTP_PROXY="http://10.113.234.119:3128"
ENV HTTPS_PROXY="http://10.113.234.119:3128"
ENV NO_PROXY="localhost,127.0.0.1"

USER root
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# --- Stage 2: Build backend ---
FROM --platform=linux/amd64 reg.navercorp.com/base/ubuntu/python:3.12 AS runtime

ENV HTTP_PROXY="http://10.113.234.119:3128"
ENV HTTPS_PROXY="http://10.113.234.119:3128"
ENV NO_PROXY="localhost,127.0.0.1"

USER root

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache .

RUN mkdir -p /app/data/logs /app/data/chroma /app/.workspaces \
    && chmod -R 777 /app/data /app/.workspaces

# Copy frontend build output
COPY --from=frontend /app/apps/web/dist ./static

EXPOSE 8000

CMD ["uvicorn", "work_harness.main:app", "--host", "0.0.0.0", "--port", "8000"]
