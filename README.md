# Lapsora

Self-hosted RTSP timelapse web application. Capture frames from RTSP cameras on a schedule, generate timelapse videos automatically, and manage everything through a modern web UI.

## Features

- **RTSP Stream Management** — Add and manage RTSP camera streams with encrypted credential storage
- **Scheduled Capture** — Configurable capture profiles with custom intervals, resolution, and quality
- **HDR Processing** — Synthetic exposure bracketing with Mertens fusion for enhanced frames
- **Automatic Timelapse Generation** — Daily, weekly, monthly, and yearly timelapses generated on schedule
- **Manual Generation** — Generate custom timelapses for any date range in MP4, WebM, or GIF
- **Retention Policies** — Automatic cleanup of old frames and timelapses
- **Web UI** — Dark-themed responsive dashboard built with SvelteKit 5

## Quick Start

### Docker (recommended)

```bash
# Clone the repository
git clone https://github.com/yourusername/lapsora.git
cd lapsora

# Configure environment
cp .env.example .env
# Edit .env and set a strong SECRET_KEY

# Start with Docker Compose
docker compose -f docker/docker-compose.yml up -d
```

Open http://localhost:8000 in your browser.

### Development Setup

**Backend:**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

The frontend dev server proxies API requests to the backend at localhost:8000.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | auto-generated | Encryption key for stored RTSP URLs |
| `DATA_DIR` | `data` | Directory for frames, timelapses, and database |
| `DATABASE_URL` | `sqlite:///data/lapsora.db` | SQLite database path |

Set variables with `LAPSORA_` prefix (e.g., `LAPSORA_SECRET_KEY`) or in `.env` file.

## Architecture

Single Docker container running:
- **FastAPI** backend serving REST API and static frontend
- **APScheduler** for capture scheduling and timelapse generation
- **FFmpeg** for RTSP frame capture and video encoding
- **OpenCV** for HDR processing (Mertens exposure fusion)
- **SQLite** for metadata storage

## API

All endpoints are under `/api`:

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Health check |
| `GET /api/storage` | Storage statistics |
| `CRUD /api/streams/` | Stream management |
| `POST /api/streams/{id}/test` | Test RTSP connection |
| `GET /api/streams/{id}/preview` | Live frame preview |
| `CRUD /api/streams/{id}/profiles` | Capture profiles |
| `GET /api/profiles/{id}/captures` | List captured frames |
| `GET /api/captures/{id}/image` | Serve frame image |
| `GET /api/timelapses` | List timelapses |
| `POST /api/profiles/{id}/timelapses/generate` | Manual generation |
| `GET /api/timelapses/{id}/video` | Serve video |

## License

MIT
