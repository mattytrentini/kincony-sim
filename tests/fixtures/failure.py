# SPDX-License-Identifier: MIT
import machine
import network

machine.Pin("failure-pin", machine.Pin.OUT, value=1)
network.WLAN().active(True)
raise ValueError("application failure must escape")
