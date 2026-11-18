# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Original CO16 app and drivers with one shared simulated environment."""
import asyncio
import os
import sys
from collections import namedtuple

SOURCE = "/sim/lib/kincony_co16"
Identity = namedtuple("Identity", ("machine", "version", "release"))


def identity():
    release = ".".join(str(part) for part in sys.implementation.version[:3])
    return Identity("KinCony CO16 (simulation)", "v" + release + "-unix", release)


class CO16Simulation:
    def __init__(self, host="0.0.0.0", port=8080):
        try:
            os.stat(SOURCE + "/co16_lcd.py")
        except OSError:
            raise RuntimeError("Initialize the pinned CO16 app: git submodule update --init lib/kincony_co16")
        if SOURCE not in sys.path:
            sys.path.insert(0, SOURCE)
        import main as application
        import network
        from co16 import CO16
        from co16_web import create_app
        from framebuf_canvas import DisplayServer, RGB565
        from .state import CO16State
        from .web import install

        self.application = application
        self.port = port
        self.state = CO16State(lambda: CO16(identity_provider=identity))
        self.board = self.state.board
        network.hostname("co16-sim")
        self.board.lan.config(mac=b"\x02\x00\x00\x00\x00\x16")
        self.app = create_app(self.board)
        self.display = DisplayServer(app=self.app, host=host, port=port, url_prefix="/display")
        self.screen = self.display.register(self.state.lcd.buffer, 320, 240, RGB565,
                                             byteorder="little", name="CO16 LCD (simulation)")
        self.state.lcd.on_frame = self.screen.publish
        install(self.app, self.state)

    async def _frames(self):
        while True:
            self.state.lcd.flush()
            await asyncio.sleep_ms(40)

    async def run(self):
        print("SIMULATION ONLY: CO16 digital controllers and LCD; no hardware devices.")
        print("CO16 app /   LCD /display/   Simulation controls /sim/")
        frames = asyncio.create_task(self._frames())
        try:
            await self.application.main(board=self.board, app=self.app,
                                        port=self.port, serve=self.display.start)
        finally:
            frames.cancel()
            try:
                await frames
            except asyncio.CancelledError:
                pass

    def shutdown(self):
        self.app.shutdown()
