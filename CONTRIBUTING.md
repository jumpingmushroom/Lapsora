# Contributing to Lapsora

Thanks for your interest in contributing! Lapsora is a vibecoded project — contributions that improve code quality, fix bugs, or add features are all welcome.

## Reporting Bugs & Requesting Features

Please use [GitHub Issues](https://github.com/jumpingmushroom/lapsora/issues):

- **Bugs**: Include steps to reproduce, expected vs. actual behavior, and your Docker/OS setup.
- **Feature requests**: Describe the use case and what you'd like to see.

## Development Setup

Lapsora runs entirely in Docker. You should never need to run it natively.

1. Fork and clone the repository
2. Copy `.env.example` to `.env` and set a `LAPSORA_SECRET_KEY`
3. Build and run:
   ```bash
   docker compose -f docker/docker-compose.yml build
   docker compose -f docker/docker-compose.yml up -d
   ```
4. Open http://localhost:8000

For GPU support, add the GPU override:
```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.gpu.yml up -d
```

## Pull Request Process

1. Fork the repo and create a feature branch from `main`
2. Make your changes
3. Rebuild the Docker container and verify it starts without errors
4. Test your changes in the browser
5. Open a PR against `main` with a clear description of what and why

## Code Style

**Backend (Python):**
- FastAPI with SQLAlchemy ORM patterns
- APScheduler for background jobs
- Keep services in `backend/app/services/`, routes in `backend/app/routers/`

**Frontend (Svelte/TypeScript):**
- SvelteKit 2 with Svelte 5 runes (`$state`, `$derived`, `$effect`)
- Tailwind CSS for styling
- API calls go through `frontend/src/lib/api.ts`

## Project Structure

```
backend/          FastAPI + SQLAlchemy + APScheduler
frontend/         SvelteKit 2 (Svelte 5 runes)
docker/           Dockerfile and docker-compose files
```

## Notes

- This is a vibecoded project — contributions that improve code quality, add tests, or improve error handling are especially appreciated.
- Keep changes focused. One feature or fix per PR.
- If you're unsure about an approach, open an issue to discuss it first.
