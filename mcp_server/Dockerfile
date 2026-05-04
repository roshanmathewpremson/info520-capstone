# Multi-stage Dockerfile for the ACC MCP server
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY . .

# Cloud Run injects PORT env var; uvicorn must bind to 0.0.0.0
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --workers 1
