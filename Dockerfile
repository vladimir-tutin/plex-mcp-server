FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    MCP_TRANSPORT=streamable-http

WORKDIR /app
COPY pyproject.toml README.md LICENSE plex_mcp_server.py watcher.py ./
COPY modules/ ./modules/
RUN pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 plexmcp

USER plexmcp
EXPOSE 3001
ENTRYPOINT ["plex-mcp-server"]
CMD ["--host", "0.0.0.0", "--port", "3001"]
