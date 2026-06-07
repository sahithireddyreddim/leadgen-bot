FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Use /tmp for SQLite on ephemeral hosts (Render free tier has no persistent disk)
# GitHub Actions uses DATABASE_PATH env var with cache
ENV DATABASE_PATH=/tmp/leads.db

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:${PORT:-5000}/health')"

# $PORT is injected by Render at runtime — must use shell form (not exec form)
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 2 --timeout 120 dashboard:app
