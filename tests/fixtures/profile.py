# SPDX-License-Identifier: MIT
import json
import sys

import machine
import network

bus = machine.I2C(0)
assert bus is machine.I2C(0)
assert bus.scan() == []
try:
    bus.readfrom(0x68, 1)
except OSError:
    pass
else:
    raise AssertionError("profiles must not fabricate RTC/expander devices")
with open(sys.argv[1], "w") as target:
    json.dump({"cpu_hz": machine.freq(), "sda": machine.Pin("I2C_SDA").snapshot(),
               "cs": machine.Pin("ETH_CS").snapshot(),
               "lan": network.LAN().snapshot()}, target)
