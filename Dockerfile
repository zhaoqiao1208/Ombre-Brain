# ============================================================
# Ombre Brain Docker Build (Zeabur dual-service + Supabase sync)
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
COPY supabase_inject.py ./supabase_inject.py
RUN chmod +x scripts/*.sh

# Run patches AT BUILD TIME (not runtime)
# 1. DCM fix + Supabase sync injection into gateway_state.py
# 2. DCM fix only if supabase_inject fails (it includes DCM fix too)
RUN python3 /app/supabase_inject.py

# Persistent mount point
VOLUME ["/app/buckets"]

ENV OMBRE_TRANSPORT=streamable-http
ENV OMBRE_BUCKETS_DIR=/app/buckets

EXPOSE 8000
EXPOSE 8010

# At runtime: only config setup + start services
# patch_config.py handles multi-upstream (runs after symlink)
CMD ["sh", "-c", "mkdir -p /app/persistent && cp /app/config.example.yaml /app/persistent/config.yaml && ln -sf /app/persistent/config.yaml /app/config.yaml; python3 /app/patch_config.py; python server.py & python gateway.py & wait"]
