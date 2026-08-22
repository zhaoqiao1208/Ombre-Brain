#!/usr/bin/env python3
"""Startup patch: fix daily_chat_memory issues in reflection_engine.py"""

import os
import sys

print("========== PATCH.PY STARTING ==========", file=sys.stderr, flush=True)

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

print("========== PATCH.PY DONE ==========", file=sys.stderr, flush=True)
