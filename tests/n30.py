# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Run real N30 app sessions, including reset after driven outputs and faults."""
import json
import os
import sys
import framebuf
import bootstrap

native = (os, framebuf)
with open("/sim/profiles/n30.json") as source:
    profile = json.load(source)
for session in (1, 2):
    bootstrap.run_application("/sim/tests/n30_session.py", (str(session),), profile)
    assert __import__("os") is native[0] and __import__("framebuf") is native[1]
print("PASS N30 real app, GPIO, 30-channel RTU, faults, OLED and safe session restart")
