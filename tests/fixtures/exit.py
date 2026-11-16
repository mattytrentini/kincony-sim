# SPDX-License-Identifier: MIT
import machine
import network

machine.Pin("exit-pin", machine.Pin.OUT, value=1)
network.WLAN().active(True)
raise SystemExit(23)
