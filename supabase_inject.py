#!/usr/bin/env python3
"""
Build-time patch (runs during Docker build, not runtime):
1. DCM fix in reflection_engine.py
2. Supabase sync injection into gateway_state.py
3. Change gateway port 8010->8011 in config.example.yaml
4. Set multi-upstream in config.example.yaml
"""

import os
import sys

print("========== SUPABASE_INJECT.PY STARTING ==========")

# ============================================================
# 1. DCM fix
# ============================================================
try:
    path = '/app/reflection_engine.py'
    with open(path, 'r') as f:
        code = f.read()
    def patch(code, old, new, label):
        if old not in code:
            print(f'WARN: {label} not found')
            return code
        return code.replace(old, new, 1)
    code = patch(code,
        'confidence = self._clamp(candidate.get("confidence", 0.0))\n            threshold = self.daily_chat_memory_min_confidence if min_confidence is None else min_confidence',
        'confidence = self._clamp(candidate.get("confidence", 0.75))\n            threshold = self.daily_chat_memory_min_confidence if min_confidence is None else min_confidence',
        'confidence fix')
    code = patch(code,
        '            if self._daily_chat_memory_low_value_social_noise(content, kind):\n                continue\n',
        '            # low_value_social disabled for relationship deployment\n',
        'low_value_social fix')
    code = patch(code,
        '            if not kind or kind == "love_letter":\n                continue\n',
        '            if not kind:\n                kind = "key_event"\n            if kind == "love_letter":\n                continue\n',
        'bad_kind fix')
    with open(path, 'w') as f:
        f.write(code)
    print('DCM fix applied')
except Exception as e:
    print(f'DCM fix FAILED: {e}')

# ============================================================
# 2. Supabase sync injection into gateway_state.py
# ============================================================
try:
    gw_path = '/app/gateway_state.py'
    with open(gw_path, 'r') as f:
        gw_code = f.read()
    print(f'gateway_state.py loaded, {len(gw_code)} bytes')
    if '_supabase_sync_turn' in gw_code:
        print('Supabase sync already installed, skipping')
    else:
        old_import = 'from typing import Any'
        new_import = '''from typing import Any

import urllib.request
import urllib.error
import threading
import logging

_supabase_logger = logging.getLogger("ombre_brain.supabase_sync")


def _supabase_get_env(name):
    return os.environ.get(name, "").strip()


def _supabase_is_configured():
    return bool(_supabase_get_env("OMBRE_SUPABASE_URL") and _supabase_get_env("OMBRE_SUPABASE_KEY"))


def _supabase_insert_message(content, role, conversation_id="", assistant_id=""):
    base = _supabase_get_env("OMBRE_SUPABASE_URL").rstrip("/")
    key = _supabase_get_env("OMBRE_SUPABASE_KEY")
    url = f"{base}/rest/v1/chat_messages"
    body = json.dumps({
        "content": content,
        "role": role,
        "conversation_id": conversation_id,
        "assistant_id": assistant_id,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=minimal")
    with urllib.request.urlopen(req, timeout=5) as resp:
        pass


def _supabase_sync_turn_sync(user_text, assistant_text, conversation_id, assistant_id):
    try:
        if user_text and user_text.strip():
            _supabase_insert_message(user_text.strip(), "user", conversation_id, assistant_id)
            _supabase_logger.info("Supabase wrote user message (%d chars)", len(user_text.strip()))
        if assistant_text and assistant_text.strip():
            _supabase_insert_message(assistant_text.strip(), "assistant", conversation_id, assistant_id)
            _supabase_logger.info("Supabase wrote assistant message (%d chars)", len(assistant_text.strip()))
    except urllib.error.HTTPError as exc:
        _supabase_logger.error("Supabase HTTP error: %s %s", exc.code, exc.reason)
    except Exception as exc:
        _supabase_logger.error("Supabase sync failed: %s", exc)


def _supabase_sync_turn(*, user_text, assistant_text="", conversation_id="", assistant_id=""):
    if not _supabase_is_configured():
        _supabase_logger.warning("Supabase not configured, skipping sync")
        return
    t = threading.Thread(
        target=_supabase_sync_turn_sync,
        args=(user_text, assistant_text, conversation_id, assistant_id),
        daemon=True,
    )
    t.start()'''
        if old_import in gw_code:
            gw_code = gw_code.replace(old_import, new_import, 1)
            print('Supabase imports added')
        else:
            print('WARN: import anchor not found')
        old_return = '        turn_id = int(cursor.lastrowid or 0)\n        conn.close()\n        return turn_id'
        new_return = '''        turn_id = int(cursor.lastrowid or 0)
        conn.close()
        try:
            _supabase_sync_turn(
                user_text=user_text,
                assistant_text=assistant_text,
                conversation_id=safe_session_id,
                assistant_id=safe_profile_id,
            )
        except Exception:
            pass
        return turn_id'''
        if old_return in gw_code:
            gw_code = gw_code.replace(old_return, new_return, 1)
            print('Supabase sync injected into record_conversation_turn')
        else:
            print('WARN: return anchor not found')
            lines = gw_code.split('\n')
            for i, line in enumerate(lines):
                if 'return turn_id' in line:
                    start = max(0, i-5)
                    end = min(len(lines), i+3)
                    for j in range(start, end):
                        print(f'  line {j}: {repr(lines[j])}')
        with open(gw_path, 'w') as f:
            f.write(gw_code)
        with open(gw_path, 'r') as f:
            verify = f.read()
        if '_supabase_sync_turn' in verify:
            print('VERIFIED: _supabase_sync_turn in gateway_state.py')
        else:
            print('VERIFICATION FAILED')
except Exception as e:
    print(f'Supabase sync FAILED: {e}')
    import traceback
    traceback.print_exc()

# ============================================================
# 3. Change gateway port 8010->8011 in config.example.yaml
# ============================================================
try:
    cfg_path = '/app/config.example.yaml'
    with open(cfg_path, 'r') as f:
        cfg = f.read()
    if 'port: 8011' in cfg:
        print('Port already 8011 in config.example.yaml')
    else:
        cfg = cfg.replace('port: 8010', 'port: 8011', 1)
        with open(cfg_path, 'w') as f:
            f.write(cfg)
        print('Gateway port changed to 8011 in config.example.yaml')
except Exception as e:
    print(f'Port change FAILED: {e}')

# ============================================================
# 4. Set multi-upstream in config.example.yaml
# ============================================================
try:
    cfg_path = '/app/config.example.yaml'
    with open(cfg_path, 'r') as f:
        cfg = f.read()
    if 'upstreams:' in cfg and 'refable' in cfg:
        print('Multi-upstream already configured')
    else:
        old = '  upstream_base_url: "https://opencode.ai/zen/go/v1"\n  upstream_default_model: "deepseek-v4-flash"\n  upstream_models:\n    - "deepseek-v4-flash"'
        new = '  upstreams:\n    - name: "refable"\n      protocol: "openai"\n      base_url: "https://api.refable.ai/v1"\n      api_key_env: "OMBRE_GATEWAY_REFABLE_API_KEY"\n      default_model: "gemini-3.7-flash-tiered"\n      prompt_cache: ""\n      models:\n        - id: "gemini-flash"\n          upstream_model: "gemini-3.7-flash-tiered"\n    - name: "kiro"\n      protocol: "openai"\n      base_url: "https://hk.xn--0xv303ar5c.com/v1"\n      api_key_env: "OMBRE_GATEWAY_KIRO_API_KEY"\n      default_model: "[kiro量高缓]claude-opus-4-6"\n      prompt_cache: ""\n      models:\n        - id: "claude-opus"\n          upstream_model: "[kiro量高缓]claude-opus-4-6"'
        if old in cfg:
            cfg = cfg.replace(old, new, 1)
            print('Multi-upstream replaced in config.example.yaml')
        else:
            print('WARN: upstream block not found in config.example.yaml')
        cfg = cfg.replace('  prompt_cache: "openai"', '  prompt_cache: ""', 1)
        with open(cfg_path, 'w') as f:
            f.write(cfg)
        print('Multi-upstream written to config.example.yaml')
except Exception as e:
    print(f'Multi-upstream FAILED: {e}')

print("========== SUPABASE_INJECT.PY DONE ==========")
