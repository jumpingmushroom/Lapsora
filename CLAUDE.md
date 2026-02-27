# Lapsora - Development Guidelines

## Environment

- **Never run the application natively.** Always use Docker.
- Docker Compose file: `docker/docker-compose.yml`
- Dockerfile: `docker/Dockerfile` (multi-stage: Node frontend build + Python backend)
- App runs on port 8000 (backend serves the built frontend)

## Verification Procedure

After completing any feature, fix, or change:

1. **Rebuild the Docker container:**
   ```bash
   docker compose -f docker/docker-compose.yml build
   ```

2. **Start the container and check logs:**
   ```bash
   docker compose -f docker/docker-compose.yml up -d
   docker compose -f docker/docker-compose.yml logs -f --tail=50
   ```
   Verify: no startup errors, migrations applied cleanly, scheduler starts.

3. **Test in Chrome MCP DevTools:**
   - Use the `chrome-devtools` MCP tools to navigate to `http://localhost:8000`
   - Verify cosmetic changes, bug fixes, and new features visually
   - Test interactive flows (clicks, form submissions, navigation)

4. **Commit and push once verified:**
   ```bash
   git add -A
   git commit -m "descriptive message"
   git push
   ```

## Project Structure

- `backend/` — FastAPI + SQLAlchemy + APScheduler
- `frontend/` — SvelteKit 2 (Svelte 5 runes)
- `docker/` — Dockerfile and docker-compose.yml
- Migrations: `backend/app/migrations/versions/*.sql` (auto-applied on startup)
