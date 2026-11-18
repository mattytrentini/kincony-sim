# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Consumer-visible scenarios over real TCP, I2C drivers and RGB565 pixel output."""
import asyncio
import framebuf
import json
import sys
import time
from co16_sim.app import CO16Simulation

PORT = 18766


async def request(path, method='GET', body=None, expected=200, media='application/json'):
    reader, writer = await asyncio.open_connection('127.0.0.1', PORT)
    data = b'' if body is None else json.dumps(body).encode()
    header = '%s %s HTTP/1.0\r\nHost: localhost\r\nConnection: close\r\n' % (method, path)
    if body is not None:
        header += 'Content-Type: %s\r\nContent-Length: %d\r\n' % (media, len(data))
    try:
        writer.write(header.encode() + b'\r\n' + data)
        await writer.drain()
        raw = await reader.read()
    finally:
        writer.close()
        await writer.wait_closed()
    head, payload = raw.split(b'\r\n\r\n', 1)
    status = int(head.split(b' ')[1])
    assert status == expected, (path, status, payload)
    if expected >= 400 and path.startswith('/sim/api/'):
        assert b'cache-control: no-store' in head.lower()
    if b'application/json' in head.lower():
        return json.loads(payload)
    return payload


async def until(predicate, timeout=6):
    deadline = time.ticks_add(time.ticks_ms(), int(timeout * 1000))
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        state = await request('/sim/api/state')
        if predicate(state):
            return state
        await asyncio.sleep_ms(50)
    raise AssertionError('CO16 did not reach the expected observed state')


async def scenario():
    phase = sys.argv[1]
    simulation = CO16Simulation(host='127.0.0.1', port=PORT)
    if phase == 'lcd-failure':
        simulation.state.lcd.online = False
    pixels = framebuf.FrameBuffer(simulation.state.lcd.buffer, 320, 240, framebuf.RGB565)
    server = asyncio.create_task(simulation.run())
    try:
        deadline = time.ticks_add(time.ticks_ms(), 5000)
        while True:
            if server.done():
                await server
            try:
                state = await request('/sim/api/state')
                break
            except OSError:
                assert time.ticks_diff(deadline, time.ticks_ms()) > 0
                await asyncio.sleep_ms(20)
        io = await request('/api/v1/io')
        assert io['relays']['raw'] == 0xFFFF and not any(io['relays']['on'])
        assert io['inputs']['raw'] == 0xFFFF and not any(io['inputs']['active'])
        assert state['inputs']['config'] == 0xFFFF and state['inputs']['polarity'] == 0
        assert state['devices']['rtc']['osf'] is False
        for device in ('relays', 'inputs', 'rtc'):
            assert state['devices'][device]['writes'] == 0
        await request('/api/v1/time')
        await request('/api/v1/status')
        assert b'CO16' in await request('/')
        await request('/sim/')
        await request('/display/')
        await request('/display/static/framebuf-canvas.js')
        if phase == 'lcd-failure':
            await until(lambda value: value['observed']['lcd_task'] == 'unavailable')
            await request('/sim/api/devices/lcd', 'POST', {'online': True})
            assert (await request('/sim/api/state'))['observed']['lcd_task'] == 'unavailable'
            assert (await request('/api/v1/relays/1'))['on'] is False
            print('PASS fatal LCD initialization failure leaves HTTP/IO alive, with no hidden restart')
            return

        # Real HTTP responds during the two-second logo, before the channel grid.
        if phase == 'exercise':
            assert pixels.pixel(10, 146) != 0x18E3
        await until(lambda value: pixels.pixel(10, 146) == 0x18E3 and pixels.pixel(10, 214) == 0x18E3)
        state = await request('/sim/api/state')
        assert state['observed']['lcd_task'] == 'running'
        for device in ('relays', 'inputs', 'rtc'):
            assert state['devices'][device]['writes'] == 0
        print('PASS safe initial relays/inputs, actual RGB565 LCD, HTTP during logo and read-only startup')
        if phase == 'restart':
            assert state['devices']['rtc']['datetime'].startswith('2026-01-01T')
            return

        expected = 0xFFFF
        for channel in range(1, 17):
            assert (await request('/api/v1/relays/%d' % channel, 'POST', {'on': True}))['on'] is True
            expected &= ~(1 << (channel - 1))
            assert (await request('/api/v1/io'))['relays']['raw'] == expected
        await until(lambda value: pixels.pixel(10, 146) == 0x0280)
        for channel in range(1, 17):
            active = [index == channel - 1 for index in range(16)]
            state = await request('/sim/api/inputs', 'POST', {'active': active})
            observed = state['observed']['io']['value']
            assert observed['inputs']['active'] == active
            assert observed['inputs']['raw'] == (0xFFFF ^ (1 << (channel - 1)))
        active = [index in (0, 5, 15) for index in range(16)]
        state = await request('/sim/api/inputs', 'POST', {'active': active, 'polarity': 0xA55A})
        assert state['observed']['io']['value']['inputs']['active'] == active
        await until(lambda value: pixels.pixel(10, 214) == 0x03AE)
        print('PASS all sixteen active-low relay bits, unrelated-bit preservation and input/polarity decoding')

        before = state['inputs']
        await request('/sim/api/inputs', 'POST', {'config': 0, 'active': [True] * 15}, expected=400)
        await request('/sim/api/inputs', 'POST', {'config': True}, expected=400)
        await request('/sim/api/inputs', 'POST', {'polarity': 65536}, expected=400)
        await request('/sim/api/inputs', 'POST', {'unknown': 0}, expected=400)
        assert (await request('/sim/api/state'))['inputs'] == before
        await request('/sim/api/inputs', 'POST', {'active': active}, expected=415, media='text/plain')
        await request('/sim/api/devices/missing', 'POST', {'online': False}, expected=404)
        assert (await request('/sim/api/missing', expected=404))['error']['code'] == 'not_found'
        assert (await request('/sim/api/state', 'POST', {}, expected=405))['error']['code'] == 'method_not_allowed'
        await request('/sim/api/inputs', expected=405)
        await request('/sim/api/inputs', 'POST', {'config': 0xFFFE})
        await request('/api/v1/io', expected=503)
        state = await until(lambda value: pixels.pixel(8, 128) == 0xF986)
        assert not state['observed']['io']['available'] and state['observed']['io']['value'] is None
        await request('/sim/api/inputs', 'POST', {'config': 0xFFFF})
        assert (await request('/api/v1/io'))['inputs']['active'] == active
        await until(lambda value: pixels.pixel(8, 128) == 0xAD75)
        print('PASS atomic validation, accurate HTTP method errors and unavailable LCD IO instead of false OFF')

        for device in ('relays', 'inputs'):
            await request('/sim/api/devices/' + device, 'POST', {'online': False})
            await request('/api/v1/io', expected=503)
            assert not (await request('/sim/api/state'))['observed']['io']['available']
            await request('/api/v1/time')
            await request('/sim/api/devices/' + device, 'POST', {'online': True})
            assert (await request('/api/v1/io'))['relays']['raw'] == expected
        await request('/sim/api/devices/rtc', 'POST', {'online': False})
        await request('/api/v1/time', expected=503)
        assert (await request('/sim/api/state'))['observed']['clock']['value'] is None
        await request('/api/v1/io')
        await request('/sim/api/devices/rtc', 'POST', {'online': True})
        await request('/sim/api/rtc', 'POST', {'osf': True})
        assert (await request('/api/v1/time'))['valid'] is False
        state = await request('/sim/api/state')
        writes = state['devices']['rtc']['writes']
        await request('/api/v1/time')
        assert (await request('/sim/api/state'))['devices']['rtc']['writes'] == writes
        clock = await request('/api/v1/time', 'POST', {'datetime': '2028-02-28T23:59:59'})
        assert clock['valid'] is True
        await until(lambda value: value['observed']['clock']['value']['datetime'].startswith('2028-02-29T00:00:'))
        print('PASS independent I2C fault recovery, readonly RTC/OSF, real clock setting and ticking leap midnight')

        await request('/sim/api/inputs', 'POST', {'config': 0})
        await request('/sim/api/devices/rtc', 'POST', {'online': False})
        print('PASS leave energized virtual relays, altered inputs/RTC and faults for safe restart regression')
    finally:
        simulation.shutdown()
        await server
        assert simulation.board.lcd_state in ('stopped', 'unavailable')


asyncio.run(scenario())
