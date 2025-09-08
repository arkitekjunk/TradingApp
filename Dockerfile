# Multi-stage build for production-ready container

# Stage 1: Build the React frontend
FROM node:18-alpine AS frontend-builder

WORKDIR /app/ui

# Copy package files
COPY ui/package.json ui/package-lock.json* ./

# Install dependencies
RUN npm ci --only=production

# Copy source code
COPY ui/ ./

# Build the frontend
RUN npm run build

# Stage 2: Python backend with built frontend
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY settings.yaml .

# Copy built frontend from stage 1
COPY --from=frontend-builder /app/ui/dist ./static

# Create data directory
RUN mkdir -p data/candles data/cache logs

# Create non-root user
RUN groupadd -r trading && useradd -r -g trading trading

# Set ownership
RUN chown -R trading:trading /app

# Switch to non-root user
USER trading

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/healthz', timeout=5)"

# Default command
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]