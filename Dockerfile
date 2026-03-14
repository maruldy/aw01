FROM python:3.12-slim AS runtime

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir uv \
    && uv pip install --system --no-cache .

EXPOSE 8000

CMD ["uvicorn", "work_harness.main:app", "--host", "0.0.0.0", "--port", "8000"]
