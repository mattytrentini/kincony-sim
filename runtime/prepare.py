# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Explicit networked preparation; runtime never invokes mip."""
import json
import sys

import mip

with open("/sim/dependencies.json") as source:
    manifest = json.load(source)
if set(manifest) != {"deps"}:
    raise ValueError("dependencies.json must be a deps-only mip manifest")
for package, revision in manifest["deps"]:
    if not package.startswith("github:") or len(revision) != 40 or any(
        character not in "0123456789abcdef" for character in revision
    ):
        raise ValueError("dependencies must use full immutable GitHub revisions")
    mip.install(package, version=revision, target="/install", mpy=False)

# mip.install may only print a failed download. Never bless a partial install:
# this is a fresh staging directory, with imports searched there before frozen.
sys.path.insert(0, "/install")
import mock_machine
import mock_network
import framebuf
from framebuf_canvas import DisplayServer
from framebuf_canvas.framebuffer import FrameBuffer

for module, names in ((mock_machine, ("reset_simulation", "register_as_machine", "freq")),
                      (mock_network, ("reset_simulation", "register_as_network", "LAN", "WLAN"))):
    for name in names:
        getattr(module, name)
for name in ("configure_aliases", "inject", "snapshot"):
    getattr(mock_machine.Pin, name)
getattr(mock_machine.UART, "set_responder")
if not issubclass(FrameBuffer, framebuf.FrameBuffer):
    raise RuntimeError("framebuf_canvas must retain native framebuf")
for asset in ("framebuf_canvas/static/index.html", "framebuf_canvas/static/app.js",
              "framebuf_canvas/static/framebuf-canvas.js", "framebuf_canvas/LICENSE",
              "microdot/LICENSE", "licenses/micropython-mock-machine.txt"):
    with open("/install/" + asset, "rb") as source:
        if not source.read(1):
            raise RuntimeError("empty dependency asset: " + asset)
print("Prepared immutable dependencies and native framebuffer support")
