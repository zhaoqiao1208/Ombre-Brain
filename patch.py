#!/usr/bin/env python3
"""Startup patch: fix daily_chat_memory + install Supabase sync into gateway_state.py"""

import os
import sys

print("========== PATCH.PY STARTING ==========", file=sys.stderr, flush=True)

# Check env vars
supabase_url = os.environ.get("OMBRE_SUPABASE_URL", "").strip()
supabase_key = os.environ.get("OMBRE_SUPABASE_KEY", "").strip()
print(f"PATCH: OMBRE_SUPABASE_URL = {'SET (' + supabase_url[:30] + '...)' if supabase_url else 'NOT SET'}", file=sys.stderr, flush=True)
print(f"PATCH: OMBRE_SUPABASE_KEY = {'SET (' + supabase_key[:10] + '...)' if supabase_key else 'NOT SET'}", file=sys.stderr, flush=True)

# ============================================================
# 1. Fix daily_chat_memory issues in reflection_engine.py
# ============================================================

try:
    path = '/app/reflection_engine.py'
    with open(path, 'r') as f:
        code = f.read()

    def patch(code, old, new, label):
        if old not in code:
            print(f'PATCH: WARN: {label} not found', file=sys.stderr, flush=True)
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
    print('PATCH: DCM fix applied', file=sys.stderr, flush=True)
except Exception as e:
    print(f'PATCH: DCM fix FAILED: {e}', file=sys.stderr, flush=True)

# ============================================================
# 2. Install Supabase sync into gateway_state.py
# ============================================================

try:
    gw_path = '/app/gateway_state.py'
    with open(gw_path, 'r') as f:
        gw_code = f.read()

    print(f'PATCH: gateway_state.py loaded, {len(gw_code)} bytes', file=sys.stderr, flush=True)

    if 'supabase_sync' in gw_code:
        print('PATCH: Supabase sync already installed, skipping', file=sys.stderr, flush=True)
    else:
        # Add imports and helper functions after 'from typing import Any'
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
        if assistant_text and assistant_text.strip():
            _supabase_insert_message(assistant_text.strip(), "assistant", conversation_id, assistant_id)
    except urllib.error.HTTPError as exc:
        _supabase_logger.warning("Supabase sync HTTP error: %s %s", exc.code, exc.reason)
    except Exception as exc:
        _supabase_logger.warning("Supabase sync failed: %s", exc)


def _supabase_sync_turn(*, user_text, assistant_text="", conversation_id="", assistant_id=""):
    if not _supabase_is_configured():
        return
    t = threading.Thread(
        target=_supabase_sync_turn_sync,
        args=(user_text, assistant_text, conversation_id, assistant_id),
        daemon=True,
    )
    t.start()'''

        if old_import in gw_code:
            gw_code = gw_code.replace(old_import, new_import, 1)
            print('PATCH: Supabase imports added', file=sys.stderr, flush=True)
        else:
            print('PATCH: WARN: import anchor not found', file=sys.stderr, flush=True)

        # Patch record_conversation_turn: insert Supabase sync before return
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
            print('PATCH: Supabase sync hook injected into record_conversation_turn', file=sys.stderr, flush=True)
        else:
            print('PATCH: WARN: return anchor not found in gateway_state.py', file=sys.stderr, flush=True)
            # Try to find what the actual return looks like
            import re
            returns = re.findall(r'.*return.*turn_id.*', gw_code)
            for r in returns:
                print(f'PATCH: found return line: {repr(r)}', file=sys.stderr, flush=True)

        with open(gw_path, 'w') as f:
            f.write(gw_code)
        print('PATCH: Supabase sync written to gateway_state.py', file=sys.stderr, flush=True)

        # Verify the patch
        with open(gw_path, 'r') as f:
            verify = f.read()
        if '_supabase_sync_turn' in verify:
            print('PATCH: VERIFIED: _supabase_sync_turn found in gateway_state.py', file=sys.stderr, flush=True)
        else:
            print('PATCH: VERIFICATION FAILED: _supabase_sync_turn NOT found after write', file=sys.stderr, flush=True)

except Exception as e:
    print(f'PATCH: Supabase sync FAILED: {e}', file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc(file=sys.stderr)

print("========== PATCH.PY DONE ==========", file=sys.stderr, flush=True)
