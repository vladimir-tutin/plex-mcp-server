FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV MCP_HOST=0.0.0.0

EXPOSE 3001

ENTRYPOINT ["python", "plex_mcp_server.py"]
