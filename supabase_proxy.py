#!/usr/bin/env python3
"""
Supabase Proxy — reverse proxy on port 8010, forwards to Ombre Gateway on 8011.
Intercepts every chat request/response and mirrors to Supabase.
Works regardless of tool_calls or record_conversation_turn skipping.
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

def _is_configured():
    return bool(_get_env("OMBRE_SUPABASE_URL") and _get_env("OMBRE_SUPABASE_KEY"))

def _insert_row(content, role, conversation_id="", assistant_id=""):
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
    with urllib.request.urlopen(req, timeout=5):
        pass

def _sync(user_text, assistant_text, conv_id, asst_id):
    if not _is_configured():
        logger.warning("Supabase not configured, skipping")
        return
    try:
        if user_text and user_text.strip():
            _insert_row(user_text.strip(), "user", conv_id, asst_id)
            logger.info("Wrote user message (%d chars)", len(user_text.strip()))
        if assistant_text and assistant_text.strip():
            _insert_row(assistant_text.strip(), "assistant", conv_id, asst_id)
            logger.info("Wrote assistant message (%d chars)", len(assistant_text.strip()))
    except urllib.error.HTTPError as exc:
        logger.error("HTTP error: %s %s", exc.code, exc.reason)
    except Exception as exc:
        logger.error("Sync failed: %s", exc)

def _extract_user_text(body):
    messages = body.get("messages") if isinstance(body, dict) else None
    if not isinstance(messages, list):
        return ""
    user_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "user"]
    if not user_msgs:
        return ""
    content = user_msgs[-1].get("content", "")
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

def _extract_assistant_from_chunk(data):
    try:
        obj = json.loads(data) if isinstance(data, str) else data
        choice = obj.get("choices", [{}])[0] if isinstance(obj, dict) else {}
        delta = choice.get("delta", {}) if isinstance(choice, dict) else {}
        return delta.get("content", "") or ""
    except Exception:
        return ""

def _extract_assistant_nonstream(body):
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

    def _proxy_get(self):
        url = f"http://{UPSTREAM_HOST}:{UPSTREAM_PORT}{self.path}"
        req = urllib.request.Request(url, method="GET")
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "transfer-encoding"):
                req.add_header(k, v)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            body = resp.read()
            self.send_response(resp.status)
            for k, v in resp.headers.items():
                if k.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            logger.error("GET proxy error: %s", exc)
            err = json.dumps({"error": str(exc)}).encode()
            self.send_response(502)
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def do_GET(self):
        self._proxy_get()

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
        for k, v in self.headers.items():
            if k.lower() not in ("host", "content-length", "transfer-encoding"):
                req.add_header(k, v)

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
            logger.error("Upstream error: %s", exc)
            err = json.dumps({"error": str(exc)}).encode()
            self.send_response(502)
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
                            aggregated += _extract_assistant_from_chunk(payload)
            except Exception as exc:
                logger.error("Stream error: %s", exc)
            finally:
                try:
                    self.wfile.flush()
                except Exception:
                    pass

            threading.Thread(
                target=_sync,
                args=(user_text, aggregated, session_id, assistant_id),
                daemon=True,
            ).start()
            logger.info("Stream completed, synced user=%d chars assistant=%d chars",
                        len(user_text or ""), len(aggregated or ""))
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
                assistant_text = _extract_assistant_nonstream(resp_json)
            except Exception:
                assistant_text = ""

            threading.Thread(
                target=_sync,
                args=(user_text, assistant_text, session_id, assistant_id),
                daemon=True,
            ).start()
            logger.info("Non-stream completed, synced user=%d chars assistant=%d chars",
                        len(user_text or ""), len(assistant_text or ""))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.end_headers()

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)


def main():
    logger.info("Starting on port %d, forwarding to %s:%d", LISTEN_PORT, UPSTREAM_HOST, UPSTREAM_PORT)
    logger.info("Supabase configured: %s", _is_configured())
    server = HTTPServer(("0.0.0.0", LISTEN_PORT), ProxyHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
