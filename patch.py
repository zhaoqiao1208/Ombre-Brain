#!/usr/bin/env python3
"""Startup patch: fix daily_chat_memory + install Supabase sync into gateway_state.py"""

import os

# ============================================================
# 1. Fix daily_chat_memory issues in reflection_engine.py
# ============================================================

path = '/app/reflection_engine.py'
with open(path, 'r') as f:
    code = f.read()

def patch(code, old, new, label):
    if old not in code:
        print(f'WARN: {label} not found')
        return code
    return code.replace(old, new, 1)

# Fix 1: confidence default 0.0 -> 0.75
code = patch(code,
    'confidence = self._clamp(candidate.get("confidence", 0.0))\n            threshold = self.daily_chat_memory_min_confidence if min_confidence is None else min_confidence',
    'confidence = self._clamp(candidate.get("confidence", 0.75))\n            threshold = self.daily_chat_memory_min_confidence if min_confidence is None else min_confidence',
    'confidence fix')

# Fix 2: disable low_value_social filter
code = patch(code,
    '            if self._daily_chat_memory_low_value_social_noise(content, kind):\n                continue\n',
    '            # low_value_social disabled for relationship deployment\n',
    'low_value_social fix')

# Fix 3: bad_kind fallback to key_event
code = patch(code,
    '            if not kind or kind == "love_letter":\n                continue\n',
    '            if not kind:\n                kind = "key_event"\n            if kind == "love_letter":\n                continue\n',
    'bad_kind fix')

with open(path, 'w') as f:
    f.write(code)
print('DCM fix patch applied')

# ============================================================
# 2. Install Supabase sync into gateway_state.py
# ============================================================

gw_path = '/app/gateway_state.py'
with open(gw_path, 'r') as f:
    gw_code = f.read()

# Idempotency: skip if already patched
if 'supabase_sync' in gw_code:
    print('Supabase sync already installed in gateway_state.py, skipping')
else:
    # Add import at the top (after existing imports)
    old_import = 'from typing import Any'
    new_import = 'from typing import Any\n\nimport json\nimport urllib.request\nimport urllib.error\nimport threading\nimport logging\n\n_supabase_logger = logging.getLogger("ombre_brain.supabase_sync")\n\n\ndef _supabase_get_env(name):\n    return os.environ.get(name, "").strip()\n\n\ndef _supabase_is_configured():\n    return bool(_supabase_get_env("OMBRE_SUPABASE_URL") and _supabase_get_env("OMBRE_SUPABASE_KEY"))\n\n\ndef _supabase_insert_message(content, role, conversation_id="", assistant_id=""):\n    base = _supabase_get_env("OMBRE_SUPABASE_URL").rstrip("/")\n    key = _supabase_get_env("OMBRE_SUPABASE_KEY")\n    url = f"{base}/rest/v1/chat_messages"\n    body = json.dumps({\n        "content": content,\n        "role": role,\n        "conversation_id": conversation_id,\n        "assistant_id": assistant_id,\n    }, ensure_ascii=False).encode("utf-8")\n    req = urllib.request.Request(url, data=body, method="POST")\n    req.add_header("apikey", key)\n    req.add_header("Authorization", f"Bearer {key}")\n    req.add_header("Content-Type", "application/json")\n    req.add_header("Prefer", "return=minimal")\n    with urllib.request.urlopen(req, timeout=5) as resp:\n        pass\n\n\ndef _supabase_sync_turn_sync(user_text, assistant_text, conversation_id, assistant_id):\n    try:\n        if user_text and user_text.strip():\n            _supabase_insert_message(user_text.strip(), "user", conversation_id, assistant_id)\n        if assistant_text and assistant_text.strip():\n            _supabase_insert_message(assistant_text.strip(), "assistant", conversation_id, assistant_id)\n    except urllib.error.HTTPError as exc:\n        _supabase_logger.warning("Supabase sync HTTP error: %s %s", exc.code, exc.reason)\n    except Exception as exc:\n        _supabase_logger.warning("Supabase sync failed: %s", exc)\n\n\ndef _supabase_sync_turn(*, user_text, assistant_text="", conversation_id="", assistant_id=""):\n    if not _supabase_is_configured():\n        return\n    t = threading.Thread(\n        target=_supabase_sync_turn_sync,\n        args=(user_text, assistant_text, conversation_id, assistant_id),\n        daemon=True,\n    )\n    t.start()'
    if old_import in gw_code:
        gw_code = gw_code.replace(old_import, new_import, 1)
        print('Supabase sync imports added to gateway_state.py')
    else:
        print('WARN: could not find import anchor in gateway_state.py')

    # Patch record_conversation_turn: insert Supabase sync before return
    old_return = '        turn_id = int(cursor.lastrowid or 0)\n        conn.close()\n        return turn_id'
    new_return = '        turn_id = int(cursor.lastrowid or 0)\n        conn.close()\n        try:\n            _supabase_sync_turn(\n                user_text=user_text,\n                assistant_text=assistant_text,\n                conversation_id=safe_session_id,\n                assistant_id=safe_profile_id,\n            )\n        except Exception:\n            pass\n        return turn_id'
    if old_return in gw_code:
        gw_code = gw_code.replace(old_return, new_return, 1)
        print('Supabase sync hook injected into record_conversation_turn')
    else:
        print('WARN: could not find return anchor in gateway_state.py')

    with open(gw_path, 'w') as f:
        f.write(gw_code)
    print('Supabase sync patch applied to gateway_state.py')
