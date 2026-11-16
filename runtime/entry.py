# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
import json
import sys

from bootstrap import run_application

with open(sys.argv[1]) as source:
    profile = json.load(source)
run_application(sys.argv[2], sys.argv[3:], profile)
