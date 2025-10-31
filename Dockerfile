# Stage 1: Install uv + build virtual environment
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_DOWNLOADS=0

# Set workdir
WORKDIR /app

# ---- 1. Install only third-party deps (cached) ----
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ---- 2. Copy source + install the project itself ----
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --all-extras


# Stage 2: Runtime image (minimal)
FROM python:3.13-slim-bookworm

# Copy the complete virtual environment
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    PYTHONUNBUFFERED=1

EXPOSE 3001

WORKDIR /app

CMD ["python", "plex_mcp_server.py", "--transport", "sse", "--host", "0.0.0.0", "--port", "3001"]
