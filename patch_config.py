#!/usr/bin/env python3
"""
Startup patch: configure multi-upstream gateway in config.yaml
Runs AFTER the config.yaml symlink is set up.
Does NOT change gateway port (stays 8010).
"""

import os
import sys

print("========== PATCH_CONFIG.PY STARTING ==========", file=sys.stderr, flush=True)

path = '/app/config.yaml'
if not os.path.exists(path):
    print('PATCH_CONFIG: WARN: config.yaml not found', file=sys.stderr, flush=True)
    sys.exit(0)

with open(path, 'r') as f:
    content = f.read()

print(f'PATCH_CONFIG: config.yaml loaded, {len(content)} bytes', file=sys.stderr, flush=True)

# Idempotency: skip if already patched
if 'upstreams:' in content and 'refable' in content:
    print('PATCH_CONFIG: multi-upstream already configured', file=sys.stderr, flush=True)
else:
    old = '  upstream_base_url: "https://opencode.ai/zen/go/v1"\n  upstream_default_model: "deepseek-v4-flash"\n  upstream_models:\n    - "deepseek-v4-flash"'

    new = '  upstreams:\n    - name: "refable"\n      protocol: "openai"\n      base_url: "https://api.refable.ai/v1"\n      api_key_env: "OMBRE_GATEWAY_REFABLE_API_KEY"\n      default_model: "gemini-3.7-flash-tiered"\n      prompt_cache: ""\n      models:\n        - id: "gemini-flash"\n          upstream_model: "gemini-3.7-flash-tiered"\n    - name: "kiro"\n      protocol: "openai"\n      base_url: "https://hk.xn--0xv303ar5c.com/v1"\n      api_key_env: "OMBRE_GATEWAY_KIRO_API_KEY"\n      default_model: "[kiro量高缓]claude-opus-4-6"\n      prompt_cache: ""\n      models:\n        - id: "claude-opus"\n          upstream_model: "[kiro量高缓]claude-opus-4-6"'

    if old in content:
        content = content.replace(old, new, 1)
        print('PATCH_CONFIG: multi-upstream replaced', file=sys.stderr, flush=True)
    else:
        print('PATCH_CONFIG: WARN: upstream block not found', file=sys.stderr, flush=True)

    content = content.replace('  prompt_cache: "openai"', '  prompt_cache: ""', 1)

with open(path, 'w') as f:
    f.write(content)

print("========== PATCH_CONFIG.PY DONE ==========", file=sys.stderr, flush=True)
