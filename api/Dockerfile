# Tenderly API - FastAPI on Python 3.11, managed with uv (CLAUDE.md stack).
FROM python:3.11-slim

# uv's official static binary, pinned by tag - no network call to a package
# index needed just to get uv itself.
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

# Install deps first (better layer caching), then copy the rest of the app.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uv", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]