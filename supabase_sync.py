#!/usr/bin/env python3
"""
Supabase chat_messages sync.
Hooks into GatewayStateStore.record_conversation_turn via sitecustomize.py.
Writes each user/assistant message to Supabase chat_messages table.

Env vars:
  OMBRE_SUPABASE_URL  — e.g. https://xxx.supabase.co
  OMBRE_SUPABASE_KEY  — anon key or service role key
"""

import json
import logging
import os
import threading
import urllib.request
import urllib.error

logger = logging.getLogger("ombre_brain.supabase_sync")


def _get_env(name: str) -> str:
    return os.environ.get(name, "").strip()


def _is_configured() -> bool:
    return bool(_get_env("OMBRE_SUPABASE_URL") and _get_env("OMBRE_SUPABASE_KEY"))


def _insert_message(content: str, role: str, conversation_id: str = "", assistant_id: str = "") -> None:
    """Insert a single message into Supabase chat_messages table via REST API."""
    base = _get_env("OMBRE_SUPABASE_URL").rstrip("/")
    key = _get_env("OMBRE_SUPABASE_KEY")
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
        return


def _sync_turn_sync(user_text: str, assistant_text: str, conversation_id: str, assistant_id: str) -> None:
    """Sync a conversation turn to Supabase. Called in a background thread."""
    try:
        if user_text and user_text.strip():
            _insert_message(user_text.strip(), "user", conversation_id, assistant_id)
        if assistant_text and assistant_text.strip():
            _insert_message(assistant_text.strip(), "assistant", conversation_id, assistant_id)
    except urllib.error.HTTPError as exc:
        logger.warning("Supabase sync HTTP error: %s %s", exc.code, exc.reason)
    except Exception as exc:
        logger.warning("Supabase sync failed: %s", exc)


def sync_turn(*, user_text: str, assistant_text: str = "", conversation_id: str = "", assistant_id: str = "") -> None:
    """Sync a conversation turn to Supabase in a background thread.

    Non-blocking: returns immediately, writes happen in daemon thread.
    Fail-soft: errors are logged but never propagated to caller.
    """
    if not _is_configured():
        return
    thread = threading.Thread(
        target=_sync_turn_sync,
        args=(user_text, assistant_text, conversation_id, assistant_id),
        daemon=True,
    )
    thread.start()


if __name__ == "__main__":
    # --- Self-test ---
    import sys
    if not _is_configured():
        print("OMBRE_SUPABASE_URL or OMBRE_SUPABASE_KEY not set; nothing to test.")
        sys.exit(0)
    print("Configured. Sending test messages...")
    _sync_turn_sync(
        user_text="[supabase_sync self-test] hello from 江屿",
        assistant_text="[supabase_sync self-test] hello from 江屿's reply",
        conversation_id="self-test",
        assistant_id="test",
    )
    print("Done. Check Supabase chat_messages table for rows with conversation_id='self-test'.")
