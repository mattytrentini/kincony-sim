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
from sim_devices.modbus import ModbusRTUSlave
from sim_devices.ssd1306 import SSD1306I2C
from sim_devices.pcf8575 import PCF8575I2C
from sim_devices.xl9535 import XL9535I2C
from sim_devices.ds3231 import DS3231I2C
from sim_devices.st7789 import ST7789SPI
from ssd1306 import SSD1306_I2C

mock_machine.register_as_machine()
from umodbus.serial import Serial
from pcf8575 import PCF8575
from xl9535 import XL9535
from ds3231 import DS3231
import st7789py
import co16_tft_config
import vga1_8x16

for module, names in ((mock_machine, ("reset_simulation", "register_as_machine", "freq")),
                      (mock_network, ("reset_simulation", "register_as_network", "LAN", "WLAN"))):
    for name in names:
        getattr(module, name)
for name in ("configure_aliases", "inject", "snapshot"):
    getattr(mock_machine.Pin, name)
getattr(mock_machine.UART, "set_responder")
getattr(mock_machine.I2C, "writevto")
getattr(mock_machine.SPI, "add_device")
getattr(mock_machine.Pin, "add_observer")
getattr(mock_machine.Pin, "remove_observer")
getattr(mock_network, "hostname")
getattr(mock_network, "ETH_CONNECTED")
getattr(ModbusRTUSlave, "respond")
getattr(SSD1306I2C, "snapshot")
getattr(PCF8575I2C, "inject")
getattr(XL9535I2C, "inject")
getattr(DS3231I2C, "set_osf")
getattr(ST7789SPI, "flush")
if not issubclass(SSD1306_I2C, framebuf.FrameBuffer):
    raise RuntimeError("SSD1306 must retain native framebuf")
for filename in ("micropython-lib.txt", "micropython-modbus.txt", "pcf8575.txt",
                 "xl9535.txt", "ds3231.txt", "st7789py.txt"):
    with open("/sim/licenses/" + filename, "rb") as source:
        with open("/install/licenses/" + filename, "wb") as target:
            target.write(source.read())
if not issubclass(FrameBuffer, framebuf.FrameBuffer):
    raise RuntimeError("framebuf_canvas must retain native framebuf")
for asset in ("framebuf_canvas/static/index.html", "framebuf_canvas/static/app.js",
              "framebuf_canvas/static/framebuf-canvas.js", "framebuf_canvas/LICENSE",
              "microdot/LICENSE", "licenses/micropython-mock-machine.txt",
              "licenses/micropython-sim-devices.txt", "licenses/micropython-lib.txt",
              "licenses/micropython-modbus.txt", "licenses/pcf8575.txt",
              "licenses/xl9535.txt", "licenses/ds3231.txt", "licenses/st7789py.txt"):
    with open("/install/" + asset, "rb") as source:
        if not source.read(1):
            raise RuntimeError("empty dependency asset: " + asset)
print("Prepared immutable dependencies and native framebuffer support")
