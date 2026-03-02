# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Production image
FROM python:3.11-slim
WORKDIR /app

# Install ffmpeg
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/ ./
RUN pip install --no-cache-dir .

# Copy frontend build
COPY --from=frontend-build /build/build ./frontend/build/

# Create non-root user
RUN groupadd -r lapsora && useradd -r -g lapsora -d /app lapsora && \
    mkdir -p /app/data && chown -R lapsora:lapsora /app

USER lapsora

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
