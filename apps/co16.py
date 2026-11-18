# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Run the original CO16 application under the shared Unix bootstrap."""
import asyncio
from co16_sim.app import CO16Simulation

asyncio.run(CO16Simulation().run())
