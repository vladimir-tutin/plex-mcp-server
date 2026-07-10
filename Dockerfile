FROM python:3.12-slim

RUN pip install --no-cache-dir plex-mcp-server

EXPOSE 3001

ENTRYPOINT ["plex-mcp-server"]
