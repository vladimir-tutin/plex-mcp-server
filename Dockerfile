# Use Python base image with uv
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Set environment for build
ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

# Set workdir
WORKDIR /app

# ---- 1. Install only third-party deps (cached) ----
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# ---- 2. Copy source + install the project itself ----
COPY src ./src
COPY README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Set runtime environment to use venv
ENV PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV="/app/.venv" \
    PYTHONUNBUFFERED=1

# Expose port (default, can be overridden by FASTMCP_PORT env var)
EXPOSE 3001

# Run the MCP server (configuration via environment variables)
CMD ["python", "-m", "plex_mcp_server"]
