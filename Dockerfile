# ============================================================
# Ombre Brain Docker Build (Zeabur: Brain + Gateway + Supabase proxy)
# ============================================================

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "mcp>=1.0.0,<2.0.0"

# Cache bust: force Zeabur to rebuild ALL layers below this point
RUN echo "rebuild-2026-08-22-v2"

COPY *.py .
COPY resources ./resources
COPY scripts ./scripts
COPY dashboard.html .
COPY dashboard_assets ./dashboard_assets
COPY config.example.yaml ./config.yaml
COPY config.example.yaml ./config.example.yaml
RUN chmod +x scripts/*.sh

# BUILD-TIME patches: DCM fix + Supabase sync injection
RUN python3 /app/supabase_inject.py

VOLUME ["/app/buckets"]

ENV OMBRE_TRANSPORT=streamable-http
ENV OMBRE_BUCKETS_DIR=/app/buckets

EXPOSE 8000
EXPOSE 8010

# Runtime: Brain(8000) + Gateway(8011 from config) + SupabaseProxy(8010)
CMD ["sh", "-c", "mkdir -p /app/persistent && cp /app/config.example.yaml /app/persistent/config.yaml && ln -sf /app/persistent/config.yaml /app/config.yaml; python server.py & python gateway.py & python supabase_proxy.py & wait"]
