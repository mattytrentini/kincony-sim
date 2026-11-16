# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Exercise shared contracts, without pretending any board peripherals exist."""
import framebuf
import gc
import json
import sys
import time

import machine
import network
from bootstrap import current_profile

print("profile:", current_profile.get("name", "custom"))
print("argv:", sys.argv)
print("native Unix:", sys.platform, "heap free:", gc.mem_free())
print("virtual cpu_hz:", machine.freq())
aliases = current_profile.get("aliases", {})
if aliases:
    alias = "BOOT" if "BOOT" in aliases else sorted(aliases)[0]
    pin = machine.Pin(alias)
    assert pin is machine.Pin(aliases[alias])
    print("alias:", alias, json.dumps(pin.snapshot()))
print("LAN:", json.dumps(network.LAN().snapshot()))

# An explicitly synthetic input; never inject guessed levels onto board pins.
pin = machine.Pin("__diagnostic_input", machine.Pin.IN, pull=None)
pin.inject(0)
edges = []
pin.irq(handler=lambda source: edges.append(source.value()),
        trigger=machine.Pin.IRQ_RISING | machine.Pin.IRQ_FALLING)
pin.inject(1)
time.sleep_ms(1)
pin.inject(1)
time.sleep_ms(1)
pin.inject(0)
time.sleep_ms(1)
assert edges == [1, 0], edges
print("injected IRQ edges:", edges)

# Generic register storage, not a named sensor, expander, RTC or display chip.
i2c = machine.I2C(99)
device = machine.RegisterBasedI2CDevice(0x50, i2c, register_count=8)
i2c.writeto(0x50, b"\x02\x12\x34")
i2c.writeto(0x50, b"\x02")
registers = i2c.readfrom(0x50, 2)
assert registers == b"\x12\x34", registers
assert machine.I2C(99) is i2c
print("I2C registers:", list(registers))

uart = machine.UART(99, baudrate=19200, bits=8, parity=None, stop=1, timeout=0)
uart.set_responder(lambda data: data.upper())
assert uart.write(b"hello\n") == 6
reply = uart.readline()
assert reply == b"HELLO\n", reply
print("UART responder:", reply)

pixels = bytearray(16)
fb = framebuf.FrameBuffer(pixels, 16, 8, framebuf.MONO_HLSB)
fb.fill(0)
fb.rect(0, 0, 16, 8, 1)
fb.pixel(7, 3, 1)
assert fb.pixel(7, 3) == 1 and fb.pixel(6, 3) == 0
print("native framebuf checksum:", sum(pixels))

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("diagnostic-intent", "not-a-real-wifi-password")
assert not wlan.isconnected() and wlan.status() == network.STAT_CONNECTING
print("WLAN connect intent:", json.dumps(wlan.snapshot()))
wlan.set_link(True, ifconfig=("198.51.100.10", "255.255.255.0", "198.51.100.1", "198.51.100.53"))
assert wlan.isconnected()
print("WLAN explicit modeled link:", json.dumps(wlan.snapshot()))
print("diagnostic complete")
if len(sys.argv) > 1:
    if sys.argv[1] == "wait":
        print("waiting for stdin release")
        sys.stdin.readline()
    else:
        print("holding independent instance for", sys.argv[1], "seconds")
        time.sleep(float(sys.argv[1]))
