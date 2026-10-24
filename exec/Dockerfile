FROM python:3.12-slim

# Execution Service host agent. No database driver, no control-plane code: it only
# speaks to /internal/v1/exec/* over HTTP. git is needed to fetch pinned commits.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY fixtures ./fixtures
RUN pip install --no-cache-dir .
# SubprocessRuntime is NOT a sandbox: run this container disposable and unprivileged.
RUN useradd --create-home --uid 10001 exec && mkdir -p /work && chown exec /work
USER exec
ENV AQS_EXEC_WORKSPACE_ROOT=/work AQS_EXEC_FIXTURES_DIR=/app/fixtures
CMD ["python", "-m", "qaswarm_exec"]
