#!/usr/bin/env python3
"""
Supabase Proxy — lightweight reverse proxy that sits between the client
and Ombre Gateway, mirroring every chat turn to Supabase chat_messages.

Architecture:
  Client -> Proxy(:8010) -> Ombre Gateway(:8011) -> LLM
                |
                v
           Supabase

Env vars:
  OMBRE_SUPABASE_URL   — e.g. https://xxx.supabase.co
  OMBRE_SUPABASE_KEY   — anon key or service role key
  OMBRE_GATEWAY_TOKEN  — forwarded to Ombre Gateway as Bearer token
"""

import json
import logging
import os
import sys
import urllib.request
import urllib.error
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s supabase_proxy %(levelname)s: %(message)s")
logger = logging.getLogger("supabase_proxy")

UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 8011
LISTEN_PORT = 8010

def _get_env(name):
    return os.environ.get(name, "").strip()

def _is_supabase_configured():
    return bool(_get_env("OMBRE_SUPABASE_URL") and _get_env("OMBRE_SUPABASE_KEY"))

def _insert_supabase_row(content, role, conversation_id="", assistant_id=""):
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
        pass

def _sync_to_supabase(user_text, assistant_text, conversation_id, assistant_id):
    if not _is_supabase_configured():
        logger.warning("Supabase not configured, skipping sync")
        return
    try:
        if user_text and user_text.strip():
            _insert_supabase_row(user_text.strip(), "user", conversation_id, assistant_id)
            logger.info("Supabase: wrote user message (%d chars)", len(user_text.strip()))
        if assistant_text and assistant_text.strip():
            _insert_supabase_row(assistant_text.strip(), "assistant", conversation_id, assistant_id)
            logger.info("Supabase: wrote assistant message (%d chars)", len(assistant_text.strip()))
    except urllib.error.HTTPError as exc:
        logger.error("Supabase HTTP error: %s %s", exc.code, exc.reason)
    except Exception as exc:
        logger.error("Supabase sync failed: %s", exc)

def _extract_user_text(body):
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list):
        return ""
    user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    if not user_msgs:
        return ""
    last = user_msgs[-1]
    content = last.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return str(content or "")

def _extract_assistant_text_from_chunk(data):
    try:
        obj = json.loads(data) if isinstance(data, str) else data
        choice = obj.get("choices", [{}])[0] if isinstance(obj, dict) else {}
        delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
        return delta.get("content", "") or ""
    except Exception:
        return ""

def _extract_assistant_text_nonstream(body):
    try:
        choice = body.get("choices", [{}])[0]
        msg = choice.get("message", {})
        content = msg.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            return "\n".join(parts)
        return str(content or "")
    except Exception:
        return ""


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward_to_upstream(self, method, path):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        url = f"http://{UPSTREAM_HOST}:{UPSTREAM_PORT}{path}"
        req = urllib.request.Request(url, data=body if body else None, method=method)

        for key, val in self.headers.items():
            low = key.lower()
            if low in ("host", "content-length", "transfer-encoding"):
                continue
            req.add_header(key, val)

        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as exc:
            resp_body = exc.read()
            self.send_response(exc.code)
            for k, v in exc.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
            return None
        except Exception as exc:
            logger.error("Upstream connection failed: %s", exc)
            err = json.dumps({"error": {"message": str(exc)}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return None
        return resp

    def do_GET(self):
        resp = self._forward_to_upstream("GET", self.path)
        if resp is None:
            return
        resp_body = resp.read()
        self.send_response(resp.status)
        for k, v in resp.headers.items():
            if k.lower() not in ("transfer-encoding", "connection"):
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp_body)))
        self.end_headers()
        self.wfile.write(resp_body)

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            body_json = json.loads(body_raw) if body_raw else {}
        except Exception:
            body_json = {}

        is_stream = bool(body_json.get("stream", False)) if isinstance(body_json, dict) else False
        user_text = _extract_user_text(body_json) if isinstance(body_json, dict) else ""
        session_id = self.headers.get("X-Ombre-Session-Id", "")
        assistant_id = self.headers.get("X-Assistant-Id", "")

        url = f"http://{UPSTREAM_HOST}:{UPSTREAM_PORT}{self.path}"
        req = urllib.request.Request(url, data=body_raw, method="POST")
        for key, val in self.headers.items():
            low = key.lower()
            if low in ("host", "content-length", "transfer-encoding"):
                continue
            req.add_header(key, val)

        try:
            resp = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as exc:
            resp_body = exc.read()
            self.send_response(exc.code)
            for k, v in exc.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
            return
        except Exception as exc:
            logger.error("Upstream connection failed: %s", exc)
            err = json.dumps({"error": {"message": str(exc)}}).encode()
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return

        if is_stream:
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.end_headers()

            aggregated = ""
            buffer = ""
            try:
                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload == "[DONE]":
                                continue
                            aggregated += _extract_assistant_text_from_chunk(payload)
            except Exception as exc:
                logger.error("Stream proxy error: %s", exc)
            finally:
                try:
                    self.wfile.flush()
                except Exception:
                    pass

            threading.Thread(
                target=_sync_to_supabase,
                args=(user_text, aggregated, session_id, assistant_id),
                daemon=True,
            ).start()
        else:
            resp_body = resp.read()
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)

            try:
                resp_json = json.loads(resp_body)
                assistant_text = _extract_assistant_text_nonstream(resp_json)
            except Exception:
                assistant_text = ""

            threading.Thread(
                target=_sync_to_supabase,
                args=(user_text, assistant_text, session_id, assistant_id),
                daemon=True,
            ).start()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def main():
    logger.info("Supabase Proxy starting on port %d", LISTEN_PORT)
    logger.info("Forwarding to upstream at %s:%d", UPSTREAM_HOST, UPSTREAM_PORT)
    logger.info("Supabase configured: %s", _is_supabase_configured())
    if not _is_supabase_configured():
        logger.warning("OMBRE_SUPABASE_URL or OMBRE_SUPABASE_KEY not set!")
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
