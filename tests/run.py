# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""Stock-MicroPython behavioral tests; no host Python or test package required."""
import framebuf
import gc
import json
import os
import socket
import sys
import time

import bootstrap
import mock_machine
import mock_network

FIXTURES = "/sim/tests/fixtures/"
IP = ("192.0.2.11", "255.255.255.0", "192.0.2.1", "192.0.2.53")


def raises(exception, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except exception as error:
        return error
    raise AssertionError("expected " + str(exception))


def read_report(path):
    with open(path) as source:
        return json.load(source)


def test_bootstrap_import_order_arguments_native_modules_and_cleanup():
    native = {"framebuf": framebuf, "gc": gc, "os": os, "time": time, "socket": socket}
    argv = sys.argv[:]
    path = sys.path[:]
    cwd = os.getcwd()
    missing = object()
    original = {name: sys.modules.get(name, missing) for name in ("machine", "network")}
    # Existing module aliases must be restored, not simply deleted.
    sys.modules["machine"] = os
    sys.modules["network"] = time
    try:
        for frequency, level in ((80000000, 1), (160000000, 0)):
            profile = {"cpu_hz": frequency, "aliases": {"INPUT": 7},
                       "pins": [{"id": "INPUT", "mode": "IN", "pull": None, "level": level}],
                       "network": [{"kind": "LAN", "active": True,
                                    "connected": True, "ifconfig": IP}]}
            output = "/tmp/consumer-report.json"
            bootstrap.run_application(FIXTURES + "consumer.py", ["space in argument", output], profile)
            report = read_report(output)
            assert report["argv"] == [FIXTURES + "consumer.py", "space in argument", output]
            assert report["cpu_hz"] == frequency == report["sibling_cpu_hz"]
            assert report["pin"]["id"] == 7 and report["pin"]["value"] == level
            assert report["network"]["connected"] and report["network"]["ifconfig"][0] == IP[0]
            assert report["native_pixel"] == 1
            assert report["cwd"] == FIXTURES[:-1]
            assert "sibling" not in sys.modules
            assert sys.modules["machine"] is os and sys.modules["network"] is time
            assert sys.argv == argv and sys.path == path and os.getcwd() == cwd
            assert bootstrap.current_profile is None
            assert mock_machine.freq() == 0
            assert not mock_network.LAN().active()
            for name, module in native.items():
                assert __import__(name) is module
    finally:
        for name, value in original.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def test_application_errors_and_system_exit_are_not_swallowed():
    modules = dict(sys.modules)
    argv = sys.argv
    path = sys.path[:]
    cwd = os.getcwd()
    error = raises(ValueError, bootstrap.run_application, FIXTURES + "failure.py")
    assert str(error) == "application failure must escape"
    error = raises(SystemExit, bootstrap.run_application, FIXTURES + "exit.py")
    assert error.args == (23,)
    assert sys.argv is argv and sys.path == path and os.getcwd() == cwd
    assert dict(sys.modules) == modules
    assert mock_machine.Pin("failure-pin").value() is None
    assert mock_machine.Pin("exit-pin").value() is None
    assert not mock_network.WLAN().active()


def test_profile_failure_cleans_partial_state():
    error = raises(ValueError, bootstrap.run_application, FIXTURES + "failure.py", (),
                   {"cpu_hz": 123000000, "aliases": {"X": 9},
                    "pins": [{"id": "X", "unsupported": True}]})
    assert "unknown pin field" in str(error)
    assert mock_machine.freq() == 0
    assert mock_machine.Pin("X") is not mock_machine.Pin(9)
    assert bootstrap.current_profile is None


def test_board_configuration_profiles_are_distinct_without_fake_chips():
    for name, sda, chip_select, address in (("n30", 18, 41, "192.0.2.30"),
                                            ("co16", 8, 42, "192.0.2.16")):
        with open("/sim/profiles/" + name + ".json") as source:
            profile = json.load(source)
        output = "/tmp/profile-report.json"
        bootstrap.run_application(FIXTURES + "profile.py", [output], profile)
        report = read_report(output)
        assert report["cpu_hz"] == 240000000
        assert report["sda"]["id"] == sda and report["cs"]["id"] == chip_select
        assert report["sda"]["value"] is None and report["cs"]["value"] is None
        assert report["lan"]["connected"] and report["lan"]["ifconfig"][0] == address


def test_network_explicit_state_failure_atomicity_and_reset():
    network = mock_network
    network.reset_simulation()
    sta = network.WLAN(network.STA_IF)
    ap = network.WLAN(network.AP_IF)
    raises(OSError, sta.connect, "example", "secret")
    sta.active(True)
    sta.connect("example", "secret")
    assert not sta.isconnected() and sta.status() == network.STAT_CONNECTING
    assert network.WLAN() is sta and not ap.active()
    before = sta.snapshot()
    raises(ValueError, sta.set_link, True)
    raises(ValueError, sta.set_link, True, ifconfig=IP, status=network.STAT_CONNECT_FAIL)
    raises(ValueError, sta.set_link, False, ifconfig=("999.0.0.1",) * 4)
    assert sta.snapshot() == before
    assert "secret" not in str(before) and "example" not in str(before)
    for status in (network.STAT_NO_AP_FOUND, network.STAT_WRONG_PASSWORD,
                   network.STAT_CONNECT_FAIL, network.STAT_HANDSHAKE_TIMEOUT):
        sta.set_link(False, status=status)
        assert not sta.isconnected() and sta.status() == status
    sta.set_link(True, ifconfig=IP)
    assert sta.isconnected() and sta.status() == network.STAT_GOT_IP
    assert sta.ifconfig() == IP
    raises(ValueError, sta.ifconfig, ("0.0.0.0",) * 4)
    assert sta.isconnected() and sta.ifconfig() == IP
    sta.active(False)
    assert not sta.isconnected() and sta.status() == network.STAT_IDLE
    raises(ValueError, sta.set_link, True)
    raises(ValueError, sta.set_link, False, status=network.STAT_CONNECTING)
    sta.active(True)
    sta.set_link(True)
    sta.disconnect()
    assert sta.active() and not sta.isconnected() and sta.status() == network.STAT_IDLE
    network.reset_simulation()
    assert not sta.active() and not ap.active() and network.WLAN() is not sta
    assert network.WLAN().ifconfig()[0] == "0.0.0.0"
    assert __import__("socket") is socket


def test_generic_bus_pin_serial_and_framebuffer_demo():
    with open("/sim/profiles/generic.json") as source:
        profile = json.load(source)
    bootstrap.run_application("/sim/examples/diagnostic.py", profile=profile)
    assert mock_machine.freq() == 0 and not mock_network.WLAN().active()


for test in (test_bootstrap_import_order_arguments_native_modules_and_cleanup,
             test_application_errors_and_system_exit_are_not_swallowed,
             test_profile_failure_cleans_partial_state,
             test_board_configuration_profiles_are_distinct_without_fake_chips,
             test_network_explicit_state_failure_atomicity_and_reset,
             test_generic_bus_pin_serial_and_framebuffer_demo):
    test()
    print("PASS", test.__name__)
print("All runtime contract tests passed")
