FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install curl for healthcheck + pip deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY . /app

# Ensure data directory exists so we can mount/persist it
RUN mkdir -p /app/data

EXPOSE 5000

# Basic healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD curl -fsS http://localhost:5000/health || exit 1

# Use gunicorn for production-ish serving
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app", "--workers", "2", "--threads", "2"]
