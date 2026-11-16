# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Real native framebuf drawing, published by the pinned framebuf_canvas library."""
import framebuf

from framebuf_canvas import DisplayServer

pixels = bytearray(128 * 64 // 8)
fb = framebuf.FrameBuffer(pixels, 128, 64, framebuf.MONO_HLSB)
fb.fill(0)
fb.rect(0, 0, 128, 64, 1)
fb.text("Unix framebuf", 8, 12, 1)
fb.line(8, 32, 119, 54, 1)
server = DisplayServer(host="0.0.0.0", port=8080)
server.register(pixels, width=128, height=64, format=framebuf.MONO_HLSB,
                name="Native Unix framebuffer")
print("Display-only viewer: publish container port 8080 with ./sim run --port 8080:8080")
server.run()
