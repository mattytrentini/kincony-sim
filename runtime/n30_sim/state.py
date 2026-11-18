# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Synthetic N30 environment; decoded observations always come from the real app."""

from machine import I2C, Pin, UART
from sim_devices.modbus import ModbusRTUSlave
from sim_devices.ssd1306 import SSD1306I2C


class N30State:
    INPUTS = ((0, "Boot button (raw)"), (8, "SD detect (raw)"),
              (15, "Expansion GPIO15"), (16, "Expansion GPIO16"))

    def __init__(self, board):
        self.board = board
        self._banks = [{"currents_mA": [0] * 10, "voltage_cV": 23000,
                        "frequency_cHz": 5000, "fault": "normal"} for _ in range(3)]
        self.oled = SSD1306I2C(I2C(0), width=128, height=64, addr=0x3C)
        self.slave = ModbusRTUSlave(1, self.read_holding, fault=self.fault_for)
        UART(1).set_responder(self.slave.respond)

    def _bank(self, bank):
        if type(bank) is not int or not 1 <= bank <= 3:
            raise KeyError("Unknown meter bank")
        return self._banks[bank - 1]

    @staticmethod
    def _scaled(value, scale, maximum, label):
        if type(value) not in (int, float) or not 0 <= value <= maximum / scale:
            raise ValueError(label + " must be finite and within the register range")
        raw = int(value * scale + 0.5)
        if raw > maximum:
            raise ValueError(label + " exceeds the register range")
        return raw

    def update_bank(self, bank, payload):
        current = self._bank(bank)
        if type(payload) is not dict or not payload:
            raise ValueError("A nonempty bank update is required")
        allowed = ("currents_A", "voltage_V", "frequency_Hz", "fault")
        if any(key not in allowed for key in payload):
            raise ValueError("Unknown bank setting")
        replacement = dict(current)
        if "currents_A" in payload:
            currents = payload["currents_A"]
            if type(currents) is not list or len(currents) != 10:
                raise ValueError("currents_A must contain exactly ten currents")
            replacement["currents_mA"] = [self._scaled(value, 1000, 0xFFFFFFFF, "Current")
                                            for value in currents]
        if "voltage_V" in payload:
            replacement["voltage_cV"] = self._scaled(payload["voltage_V"], 100, 65535, "Voltage")
        if "frequency_Hz" in payload:
            replacement["frequency_cHz"] = self._scaled(payload["frequency_Hz"], 100, 65535, "Frequency")
        if "fault" in payload:
            if payload["fault"] not in ("normal", "timeout", "crc"):
                raise ValueError("Fault must be normal, timeout or crc")
            replacement["fault"] = payload["fault"]
        # Publish one complete environment update, never a partially validated bank.
        self._banks[bank - 1] = replacement

    @staticmethod
    def _range(start, count):
        for bank in range(1, 4):
            base = bank * 100
            if base <= start and start + count <= base + 68:
                return bank, start - base
        raise IndexError("No ARM register bank at this address")

    def read_holding(self, start, count):
        bank, offset = self._range(start, count)
        source = self._bank(bank)
        # Unknown ARM power/energy/temperature layouts are deliberately not modeled.
        words = [0] * 68
        for index, milliamps in enumerate(source["currents_mA"]):
            words[2 * index] = milliamps & 0xFFFF
            words[2 * index + 1] = milliamps >> 16
        words[62] = source["voltage_cV"]
        words[63] = source["frequency_cHz"]
        return words[offset:offset + count]

    def fault_for(self, start, count):
        try:
            bank, _ = self._range(start, count)
        except IndexError:
            return "normal"
        return self._bank(bank)["fault"]

    def inject_pin(self, pin, level):
        if type(pin) is not int or pin not in (0, 8, 15, 16):
            raise KeyError("Unknown input pin")
        if level is not None and (type(level) is not int or level not in (0, 1)):
            raise ValueError("Input level must be 0, 1 or null")
        gpio = Pin(pin)
        if gpio.mode() != Pin.IN:
            raise RuntimeError("Return the pin to input mode in the device UI before injecting it")
        gpio.inject(level)

    def snapshot(self):
        pins = []
        for number, name in self.INPUTS:
            raw = Pin(number).snapshot()
            output = self.board.gpio(number)["output"] if number in (15, 16) else None
            pull = raw.get("pull")
            pins.append({"pin": number, "name": name,
                         "mode": "input" if raw["mode"] == Pin.IN else "output",
                         "level": raw["value"], "output": output,
                         "pull": "none" if pull is None else "up" if pull == Pin.PULL_UP else "down"})
        return {"simulation": True, "board": "N30", "pins": pins,
                "banks": [{"bank": number, "currents_A": [value * 0.001 for value in bank["currents_mA"]],
                           "voltage_V": bank["voltage_cV"] * 0.01,
                           "frequency_Hz": bank["frequency_cHz"] * 0.01,
                           "fault": bank["fault"]}
                          for number, bank in enumerate(self._banks, 1)],
                "observed": self.board.metering(), "oled": self.oled.snapshot(),
                "modbus": self.slave.snapshot()}
