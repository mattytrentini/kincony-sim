# SPDX-License-Identifier: MIT
import json
import os
import sys

import framebuf
import machine
import network
import sibling
import __main__

MAIN_MARKER = object()
assert __main__.__file__ == __file__
assert __main__.MAIN_MARKER is MAIN_MARKER

assert sibling.Pin is machine.Pin
assert sibling.network is network
pixels = bytearray(8)
fb = framebuf.FrameBuffer(pixels, 8, 8, framebuf.MONO_HLSB)
fb.pixel(2, 3, 1)
with open(sys.argv[2], "w") as target:
    json.dump({"argv": sys.argv, "cpu_hz": machine.freq(),
               "sibling_cpu_hz": sibling.CPU_AT_IMPORT,
               "pin": machine.Pin("INPUT").snapshot(),
               "network": network.LAN().snapshot(),
               "native_pixel": fb.pixel(2, 3), "cwd": os.getcwd()}, target)
# These process-level changes must not escape the session, even on normal exit.
sys.argv[:] = ["changed-by-app"]
sys.path.append("/tmp/changed-by-app")
sys.modules["network"] = "changed-by-app"
os.chdir("/tmp")
