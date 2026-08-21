# ============================================================
# Ombre Brain Docker Build (Zeabur dual-service)
# With daily_chat_memory fix, config persistence, MCP lock
# ============================================================

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (leverage Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "mcp>=1.0.0,<2.0.0"

# Copy project files
COPY *.py .
COPY resources ./resources
COPY scripts ./scripts
COPY dashboard.html .
COPY dashboard_assets ./dashboard_assets
COPY config.example.yaml ./config.yaml
COPY config.example.yaml ./config.example.yaml
COPY patch.py ./patch.py
RUN chmod +x scripts/*.sh

# Persistent mount point
VOLUME ["/app/buckets"]

ENV OMBRE_TRANSPORT=streamable-http
ENV OMBRE_BUCKETS_DIR=/app/buckets

EXPOSE 8000
EXPOSE 8010

# 1. Apply daily_chat_memory patches
# 2. Set up persistent config.yaml via symlink
# 3. Start both Brain and Gateway
CMD ["sh", "-c", "python3 /app/patch.py; mkdir -p /app/persistent && ([ -f /app/persistent/config.yaml ] || cp /app/config.example.yaml /app/persistent/config.yaml) && ln -sf /app/persistent/config.yaml /app/config.yaml; python server.py & python gateway.py & wait"]
