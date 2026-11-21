# Escape Pod game server. Used by render.yaml; works on any Docker host.
#   docker build -t escape-pod .
#   docker run -p 8000:8000 -e METERED_APP=... -e METERED_API_KEY=... escape-pod
# The host's proxy adds HTTPS, which browsers need for the camera.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Dependencies first, so code changes do not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project

COPY src ./src
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH" \
    HOST=0.0.0.0 \
    PORT=8000
EXPOSE 8000

# Rooms live in memory: run exactly one instance.
CMD ["escape-pod"]
