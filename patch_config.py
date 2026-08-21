#!/usr/bin/env python3
"""Startup patch: configure multi-upstream gateway in config.yaml"""

import os

path = '/app/config.yaml'
if not os.path.exists(path):
    print('WARN: config.yaml not found, skipping gateway patch')
    exit(0)

with open(path, 'r') as f:
    content = f.read()

# Idempotency: skip if already patched
if 'upstreams:' in content and 'refable' in content:
    print('Gateway multi-upstream already configured, skipping')
    exit(0)

# Replace single upstream with multi-upstream
old = '  upstream_base_url: "https://opencode.ai/zen/go/v1"\n  upstream_default_model: "deepseek-v4-flash"\n  upstream_models:\n    - "deepseek-v4-flash"'

new = '  upstreams:\n    - name: "refable"\n      protocol: "openai"\n      base_url: "https://api.refable.ai/v1"\n      api_key_env: "OMBRE_GATEWAY_REFABLE_API_KEY"\n      default_model: "gemini-3.7-flash-tiered"\n      prompt_cache: ""\n      models:\n        - id: "gemini-flash"\n          upstream_model: "gemini-3.7-flash-tiered"\n    - name: "kiro"\n      protocol: "openai"\n      base_url: "https://hk.xn--0xv303ar5c.com/v1"\n      api_key_env: "OMBRE_GATEWAY_KIRO_API_KEY"\n      default_model: "[kiro量高缓]claude-opus-4-6"\n      prompt_cache: ""\n      models:\n        - id: "claude-opus"\n          upstream_model: "[kiro量高缓]claude-opus-4-6"'

if old in content:
    content = content.replace(old, new, 1)
    print('Gateway upstreams replaced')
else:
    print('WARN: upstream_base_url block not found, skipping')

# Update global prompt_cache to empty (now per-upstream)
content = content.replace('  prompt_cache: "openai"', '  prompt_cache: ""', 1)

with open(path, 'w') as f:
    f.write(content)
print('Gateway multi-upstream patch applied')
