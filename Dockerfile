# ============================================================
# Ombre Brain Docker Build (Zeabur dual-service + Supabase proxy)
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

# 1. Apply DCM fix to reflection_engine.py
# 2. ALWAYS re-copy config from source (don't trust persistent volume's old copy)
# 3. patch_config.py changes port 8010->8011 and sets multi-upstream
# 4. Start Brain(8000) + Gateway(8011) + SupabaseProxy(8010)
CMD ["sh", "-c", "python3 /app/patch.py; mkdir -p /app/persistent && cp /app/config.example.yaml /app/persistent/config.yaml && ln -sf /app/persistent/config.yaml /app/config.yaml; python3 /app/patch_config.py; python server.py & python gateway.py & python supabase_proxy.py & wait"]
