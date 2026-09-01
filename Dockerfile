# Dockerfile – Django RAG project (Gunicorn)

FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev python3-dev git curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached)
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn

# Copy source code
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput || true

# Runtime image (smaller)
FROM python:3.11-slim
WORKDIR /app

# Runtime deps (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app

ENV PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

EXPOSE 8000

# Start Gunicorn with 4 workers
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4"]
