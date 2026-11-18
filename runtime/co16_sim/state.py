# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Environmental controls; observations always use the real CO16 drivers."""
from machine import I2C, Pin, SPI
from sim_devices.pcf8575 import PCF8575I2C
from sim_devices.xl9535 import XL9535I2C
from sim_devices.ds3231 import DS3231I2C
from sim_devices.st7789 import ST7789SPI


class CO16State:
    def __init__(self, board_factory):
        bus = I2C(0)
        self.relays = PCF8575I2C(bus, addr=0x22)
        self.inputs = XL9535I2C(bus, addr=0x24)
        self.rtc = DS3231I2C(bus, addr=0x68, datetime=(2026, 1, 1, 0, 0, 0, 4), osf=False)
        self.lcd = ST7789SPI(SPI(2), cs=Pin(4), dc=Pin(0), reset=Pin(5),
                             backlight=Pin(40), width=320, height=240,
                             panel_color_order="BGR", native_inversion=True)
        self._devices = {"relays": self.relays, "inputs": self.inputs,
                         "rtc": self.rtc, "lcd": self.lcd}
        # All controllers are attached before the actual driver constructors run.
        self.board = board_factory()

    @staticmethod
    def _u16(value, name):
        if type(value) is not int or not 0 <= value <= 0xFFFF:
            raise ValueError(name + " must be an integer from 0 to 65535")
        return value

    def update_inputs(self, payload):
        if type(payload) is not dict or not payload or any(
            key not in ("active", "config", "polarity") for key in payload
        ):
            raise ValueError("Expected active, config or polarity input settings")
        raw = None
        if "active" in payload:
            active = payload["active"]
            if type(active) is not list or len(active) != 16 or any(type(value) is not bool for value in active):
                raise ValueError("active must contain exactly sixteen booleans")
            raw = 0xFFFF ^ sum(1 << index for index, value in enumerate(active) if value)
        config = self._u16(payload["config"], "config") if "config" in payload else None
        polarity = self._u16(payload["polarity"], "polarity") if "polarity" in payload else None
        if raw is not None:
            self.inputs.inject(raw)
        if config is not None:
            self.inputs.config = config
        if polarity is not None:
            self.inputs.polarity = polarity

    def update_rtc(self, payload):
        if type(payload) is not dict or set(payload) != {"osf"} or type(payload["osf"]) is not bool:
            raise ValueError("Expected an osf boolean")
        self.rtc.set_osf(payload["osf"])

    def update_device(self, device, payload):
        if device not in self._devices:
            raise KeyError("Unknown device")
        if type(payload) is not dict or set(payload) != {"online"} or type(payload["online"]) is not bool:
            raise ValueError("Expected an online boolean")
        self._devices[device].online = payload["online"]

    @staticmethod
    def _observe(read):
        try:
            return {"available": True, "value": read(), "error": None}
        except OSError as error:
            return {"available": False, "value": None, "error": str(error)}

    def snapshot(self):
        inputs = self.inputs.snapshot()
        raw = inputs["raw_levels"]
        lcd = self.lcd.snapshot()
        return {"simulation": True, "board": "CO16",
                "inputs": {"raw": raw, "active": [not bool(raw & (1 << bit)) for bit in range(16)],
                           "config": inputs["config"], "polarity": inputs["polarity"]},
                "devices": {"relays": self.relays.snapshot(), "inputs": inputs,
                            "rtc": self.rtc.snapshot(), "lcd": lcd},
                "observed": {"io": self._observe(self.board.io),
                             "clock": self._observe(self.board.clock),
                             "lcd_task": self.board.lcd_state}, "lcd": lcd}
