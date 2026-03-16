# --- Stage 1: Build frontend ---
FROM node:20-slim AS frontend

WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build

# --- Stage 2: Build backend ---
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache .

# Copy frontend build output
COPY --from=frontend /app/apps/web/dist ./static

EXPOSE 8000

CMD ["uvicorn", "work_harness.main:app", "--host", "0.0.0.0", "--port", "8000"]
