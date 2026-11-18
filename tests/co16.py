# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Real CO16 sessions: normal IO, safe restart and fatal display isolation."""
import json
import os
import framebuf
import bootstrap

native = (os, framebuf)
with open('/sim/profiles/co16.json') as source:
    profile = json.load(source)
for phase in ('exercise', 'restart', 'lcd-failure'):
    bootstrap.run_application('/sim/tests/co16_session.py', (phase,), profile)
    assert __import__('os') is native[0] and __import__('framebuf') is native[1]
print('PASS CO16 original application, real drivers, LCD, faults and safe restart')
