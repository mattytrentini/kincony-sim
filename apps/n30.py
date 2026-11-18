# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Launch the actual N30 web/OLED/meter application under the simulator bootstrap."""
import asyncio
from n30_sim.app import N30Simulation

asyncio.run(N30Simulation().run())
