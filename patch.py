#!/usr/bin/env python3
"""Startup patch: fix daily_chat_memory issues in reflection_engine.py"""

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
