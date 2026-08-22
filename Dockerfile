# ============================================================
# Ombre Brain Docker Build (Zeabur: Brain + Gateway + Supabase proxy)
# ============================================================

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir "mcp>=1.0.0,<2.0.0"

COPY *.py .
COPY resources ./resources
COPY scripts ./scripts
COPY dashboard.html .
COPY dashboard_assets ./dashboard_assets
COPY config.example.yaml ./config.yaml
COPY config.example.yaml ./config.example.yaml
RUN chmod +x scripts/*.sh

# BUILD-TIME patches: DCM fix + Supabase sync injection (may be cached)
RUN python3 /app/supabase_inject.py || true

VOLUME ["/app/buckets"]

ENV OMBRE_TRANSPORT=streamable-http
ENV OMBRE_BUCKETS_DIR=/app/buckets

EXPOSE 8000
EXPOSE 8010

# Runtime: 
# 1. Copy config to persistent
# 2. FORCE port change to 8011 with sed (works regardless of cache)
# 3. FORCE multi-upstream with sed (works regardless of cache)
# 4. Start Brain(8000) + Gateway(8011) + SupabaseProxy(8010)
CMD ["sh", "-c", "mkdir -p /app/persistent && cp /app/config.example.yaml /app/persistent/config.yaml && sed -i 's/port: 8010/port: 8011/' /app/persistent/config.yaml && if ! grep -q 'upstreams:' /app/persistent/config.yaml; then sed -i '/upstream_base_url/c\\  upstreams:\\n    - name: \"refable\"\\n      protocol: \"openai\"\\n      base_url: \"https://api.refable.ai/v1\"\\n      api_key_env: \"OMBRE_GATEWAY_REFABLE_API_KEY\"\\n      default_model: \"gemini-3.7-flash-tiered\"\\n      prompt_cache: \"\"\\n      models:\\n        - id: \"gemini-flash\"\\n          upstream_model: \"gemini-3.7-flash-tiered\"\\n    - name: \"kiro\"\\n      protocol: \"openai\"\\n      base_url: \"https://hk.xn--0xv303ar5c.com/v1\"\\n      api_key_env: \"OMBRE_GATEWAY_KIRO_API_KEY\"\\n      default_model: \"[kiro量高缓]claude-opus-4-6\"\\n      prompt_cache: \"\"\\n      models:\\n        - id: \"claude-opus\"\\n          upstream_model: \"[kiro量高缓]claude-opus-4-6\"' /app/persistent/config.yaml && sed -i 's/prompt_cache: \"openai\"/prompt_cache: \"\"/' /app/persistent/config.yaml; fi && ln -sf /app/persistent/config.yaml /app/config.yaml && python server.py & python gateway.py & python supabase_proxy.py & wait"]
