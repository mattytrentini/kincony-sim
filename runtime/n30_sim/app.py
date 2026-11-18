# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""The original N30 app, its original drivers, and shared simulated resources."""
import os
import sys
from collections import namedtuple

SOURCE = "/sim/lib/kincony_n30"
Identity = namedtuple("Identity", ("machine", "version", "release"))


def identity():
    release = ".".join(str(part) for part in sys.implementation.version[:3])
    return Identity("KinCony N30 (simulation)", sys.version, release)


class N30Simulation:
    def __init__(self, host="0.0.0.0", port=8080):
        try:
            os.stat(SOURCE + "/main.py")
        except OSError:
            raise RuntimeError("Initialize the pinned N30 app: git submodule update --init --recursive")
        if SOURCE not in sys.path:
            sys.path.insert(0, SOURCE)
        import main as application
        import network
        from n30 import N30
        from n30_web import create_app
        from framebuf_canvas import DisplayServer, MONO_VLSB
        from .state import N30State
        from .web import install

        self.application = application
        self.port = port
        self.board = N30(identity_provider=identity)
        self.state = N30State(self.board)
        network.hostname("n30-sim")
        network.LAN().config(mac=b"\x02\x00\x00\x00\x00\x30")
        self.app = create_app(self.board)
        self.display = DisplayServer(app=self.app, host=host, port=port, url_prefix="/display")
        self.screen = self.display.register(
            self.state.oled.buffer, 128, 64, MONO_VLSB, name="N30 OLED (simulation)"
        )
        self.state.oled.on_frame = self.screen.publish
        install(self.app, self.state)

    async def run(self):
        print("SIMULATION ONLY: N30 drivers use virtual GPIO, UART and OLED; no hardware devices.")
        print("N30 app /   OLED /display/   Simulation controls /sim/")
        await self.application.main(board=self.board, app=self.app,
                                    port=self.port, serve=self.display.start)

    def shutdown(self):
        self.app.shutdown()
