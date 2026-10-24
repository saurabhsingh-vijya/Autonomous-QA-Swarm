# Build context is the repository root (see docker-compose.yml) so the optional embedded
# Execution Service worker (../exec) can be installed for the local demo.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# git is required by Intake & Pinning (git ls-remote) and by the worker's source fetcher.
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*     && pip install --no-cache-dir uv==0.13.5
WORKDIR /app/backend
COPY exec /app/exec
COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
RUN uv sync --frozen --no-dev --extra embedded --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev --extra embedded
ENV PATH="/app/backend/.venv/bin:$PATH"
EXPOSE 8000
CMD ["python", "-m", "qaswarm.api.serve", "--host", "0.0.0.0", "--port", "8000"]
