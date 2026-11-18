# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Consumer-visible checks over actual TCP and the actual N30 worker lifecycle."""
import asyncio
import json
import sys
import time
from n30_sim.app import N30Simulation

PORT = 18765


async def request(path, method="GET", body=None, expected=200, media="application/json"):
    reader, writer = await asyncio.open_connection("127.0.0.1", PORT)
    data = b"" if body is None else json.dumps(body).encode()
    header = "%s %s HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n" % (method, path)
    if body is not None:
        header += "Content-Type: %s\r\nContent-Length: %d\r\n" % (media, len(data))
    try:
        writer.write(header.encode() + b"\r\n" + data)
        await writer.drain()
        raw = await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()
    head, payload = raw.split(b"\r\n\r\n", 1)
    status = int(head.split(b" ")[1])
    assert status == expected, (path, status, payload)
    if b"application/json" in head.lower():
        return json.loads(payload)
    return payload


async def until(predicate, timeout=9):
    deadline = time.ticks_add(time.ticks_ms(), int(timeout * 1000))
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        state = await request("/sim/api/state")
        if predicate(state):
            return state
        await asyncio.sleep_ms(100)
    raise AssertionError("N30 did not reach expected observed state")


def close(left, right):
    return abs(left - right) < 0.000001


def decoded(state, targets):
    for index, bank in enumerate(state["observed"]["banks"]):
        if not bank["available"]:
            return False
        target = targets[index]
        if not close(bank["voltage_V"], target["voltage_V"]) or not close(bank["frequency_Hz"], target["frequency_Hz"]):
            return False
        for offset, channel in enumerate(bank["channels"]):
            assert channel["channel"] == index * 10 + offset + 1
            if not close(channel["current_A"], target["currents_A"][offset]):
                return False
    return True


async def scenario():
    simulation = N30Simulation(host="127.0.0.1", port=PORT)
    server = asyncio.create_task(simulation.run())
    try:
        deadline = time.ticks_add(time.ticks_ms(), 3000)
        while True:
            if server.done():
                await server
            try:
                state = await request("/sim/api/state")
                break
            except OSError:
                assert time.ticks_diff(deadline, time.ticks_ms()) > 0
                await asyncio.sleep_ms(20)
        for pin in state["pins"]:
            assert pin["mode"] == "input" and pin["level"] is None and pin["output"] is None
            assert pin["pull"] == "none"
        for bank in state["banks"]:
            assert bank["currents_A"] == [0] * 10 and bank["fault"] == "normal"
            assert bank["voltage_V"] == 230 and bank["frequency_Hz"] == 50
        await until(lambda value: decoded(value, state["banks"]))
        assert b"N30" in await request("/")
        await request("/display/")
        await request("/display/static/framebuf-canvas.js")
        await request("/sim/")
        assert simulation.board.oled_state == "running"
        assert simulation.state.oled.snapshot()["frames"] >= 2
        print("PASS fresh safe GPIO state, real decoder defaults and all three HTTP surfaces")
        if sys.argv[1] == "2":
            return

        for pin in (0, 8, 15, 16):
            await request("/sim/api/inputs/%d" % pin, "POST", {"level": 1})
        assert (await request("/api/v1/gpios/15"))["level"] is True
        await request("/api/v1/gpios/15", "POST", {"mode": "output", "high": True})
        await request("/sim/api/inputs/15", "POST", {"level": 0}, expected=409)
        pin = [item for item in (await request("/sim/api/state"))["pins"] if item["pin"] == 15][0]
        assert pin["mode"] == "output" and pin["level"] == 1 and pin["output"] is True
        await request("/api/v1/gpios/15", "POST", {"mode": "input"})
        await request("/sim/api/inputs/15", "POST", {"level": None})
        await request("/sim/api/inputs/15", "POST", {"level": True}, expected=400)
        await request("/sim/api/inputs/17", "POST", {"level": 1}, expected=404)
        await request("/sim/api/inputs/16", "POST", {"level": 1}, expected=415, media="text/plain")
        print("PASS shared GPIO injection, real output controls, high impedance and conflict rejection")

        targets = []
        for bank in range(1, 4):
            currents = [bank + index * 0.125 + 0.001 for index in range(10)]
            currents[0] = 123.456 if bank == 1 else currents[0]
            if bank == 3:
                currents[9] = 4294967.295
            target = {"currents_A": currents, "voltage_V": 240.25 + bank,
                      "frequency_Hz": 49.99 + bank * 0.01, "fault": "normal"}
            await request("/sim/api/banks/%d" % bank, "POST", target)
            targets.append(target)
        state = await until(lambda value: decoded(value, targets))
        before = state["banks"][0]
        await request("/sim/api/banks/1", "POST", {"voltage_V": 1, "currents_A": [True] * 10}, expected=400)
        await request("/sim/api/banks/1", "POST", {"voltage_V": 655.36}, expected=400)
        await request("/sim/api/banks/1", "POST", {"unknown": 1}, expected=400)
        await request("/sim/api/banks/4", "POST", {"fault": "timeout"}, expected=404)
        await request("/sim/api/banks/1", expected=405)
        assert (await request("/sim/api/state"))["banks"][0] == before
        print("PASS all 30 real decoded currents, 32-bit word order/range, V/Hz and atomic validation")

        await request("/sim/api/banks/1", "POST", {"fault": "timeout"})
        await request("/sim/api/banks/2", "POST", {"fault": "crc"})
        state = await until(lambda value: not value["observed"]["banks"][0]["available"] and not value["observed"]["banks"][1]["available"])
        for bank in state["observed"]["banks"][:2]:
            assert bank["error"] and bank["voltage_V"] is None and bank["frequency_Hz"] is None
            assert all(channel["current_A"] is None for channel in bank["channels"])
        assert state["observed"]["banks"][2]["available"]
        assert state["modbus"]["crc_errors"] > 0
        for bank in (1, 2):
            await request("/sim/api/banks/%d" % bank, "POST", {"fault": "normal"})
        await until(lambda value: decoded(value, targets))
        print("PASS actual UART timeout/CRC rejection, unavailable not zero, healthy bank isolation and recovery")

        initial = bytes(simulation.state.oled.buffer)
        frames = simulation.state.oled.snapshot()["frames"]
        await until(lambda value: value["oled"]["frames"] > frames and bytes(simulation.state.oled.buffer) != initial, timeout=10)
        assert simulation.board.oled_state == "running"
        await request("/api/v1/gpios/16", "POST", {"mode": "output", "high": True})
        await request("/sim/api/banks/3", "POST", {"fault": "crc"})
        print("PASS real OLED refresh; leave driven GPIO and faults for restart regression")
    finally:
        simulation.shutdown()
        await server


asyncio.run(scenario())
