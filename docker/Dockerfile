# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# Stage 2: Production image (NVIDIA CUDA runtime for NVENC support)
FROM nvidia/cuda:12.8.1-runtime-ubuntu22.04
WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.11 via deadsnakes PPA and system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends software-properties-common gpg-agent && \
    add-apt-repository -y ppa:deadsnakes/ppa && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 python3.11-venv python3.11-dev \
        ffmpeg \
        libglib2.0-0 libgl1 \
        libx265-dev \
        libffi-dev libssl-dev \
        fonts-dejavu-core \
        cuda-cudart-dev-12-8 cuda-nvcc-12-8 \
        gosu && \
    rm -rf /var/lib/apt/lists/*

# Set python3.11 as default python
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3.11 1

# Install pip
RUN python3.11 -m ensurepip --upgrade && \
    python3.11 -m pip install --no-cache-dir --upgrade pip

# Install Python dependencies
COPY backend/ ./
RUN pip install --no-cache-dir .

# Copy frontend build
COPY --from=frontend-build /build/build ./frontend/build/

# Create non-root user
RUN groupadd -r lapsora && useradd -r -g lapsora -d /app lapsora && \
    mkdir -p /app/data && chown -R lapsora:lapsora /app

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
