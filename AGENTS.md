# Agent Instructions - docker-seafile-client

Docker container for Seafile CLI client with automatic retry logic for server outages.

## Quick Commands

### Build & Test Locally
```bash
# Build image
docker build -t snegov/seafile-client:test .

# Test locally with docker-compose
docker compose build
docker compose up

# Check logs
docker compose logs -f
```

### Build & Deploy Test Image to Docker Hub
```bash
# Build fresh image without cache
docker build --no-cache -t snegov/seafile-client:test .

# Push to Docker Hub (requires login)
docker push snegov/seafile-client:test
```

Deploying to hosts is documented in `CLAUDE.local.md` (private, not in the
repo).

### Release New Version
```bash
# Create tag; pushing it to GitHub runs the Docker Hub publish workflow
git tag 0.0.X
git push gh 0.0.X

# Docker Hub will automatically build snegov/seafile-client:latest and snegov/seafile-client:0.0.X
```

### Syntax Check
```bash
python3 -m py_compile dsc/client.py
python3 -m py_compile start.py
```

## Project Structure

```
dsc/
  client.py       - Main SeafileClient class
  const.py        - Constants
  misc.py         - Helper functions
  __init__.py     - Package init
start.py          - Container entrypoint
Dockerfile        - Image definition
docker-compose.yml - Local testing setup
requirements.txt  - Python dependencies
```

## Architecture Notes

### HTTP Retry Strategy
- 30 retry attempts with exponential backoff (2s base, 60s max)
- Retries on 500, 502, 503, 504 status codes
- Prevents container crash-loop during server outages
- urllib3 debug logging shows retry attempts

### Session Management
- Single `requests.Session` per client instance
- Retry logic configured via `HTTPAdapter` + `Retry`
- Token cached in `self.__token` (fetched on first use)

### Server URL Handling
- Assumes HTTPS unless `http://` explicitly specified
- No initial connection test (fails fast on first API call)

### Library Status Monitoring
- Dynamic column width (max 30 chars) for clean output
- Only logs status changes (not every poll)
- Handles long library names without breaking alignment

## Testing

No formal test suite yet. Manual testing via:
1. Build image
2. Run with docker-compose
3. Monitor logs for expected behavior
4. Test with server down (should retry, not crash)

## Deployment

- Production: `snegov/seafile-client:latest` (auto-built from tags)
- Testing: `snegov/seafile-client:test` (manual push)

## Common Issues

**Container crash-loops on 502**: Retry logic should handle this (check urllib3 logs).

**No retry logs visible**: Ensure urllib3 logger is set to DEBUG and propagate=True.

**Wrong image deployed**: Clear old image with `docker rmi` before pulling fresh one.
