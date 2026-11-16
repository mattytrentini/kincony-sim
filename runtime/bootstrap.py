# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
"""One isolated modeled session around an ordinary MicroPython script."""
import os
import sys

import mock_machine
import mock_network

current_profile = None


def _pin_options(configuration):
    options = {}
    if "mode" in configuration:
        mode = configuration["mode"]
        if mode not in ("IN", "OUT", "OPEN_DRAIN"):
            raise ValueError("unsupported pin mode: " + str(mode))
        options["mode"] = getattr(mock_machine.Pin, mode)
    if "pull" in configuration:
        pull = configuration["pull"]
        if pull is not None:
            if pull not in ("PULL_UP", "PULL_DOWN"):
                raise ValueError("unsupported pin pull: " + str(pull))
            pull = getattr(mock_machine.Pin, pull)
        options["pull"] = pull
    return options


def apply_profile(profile):
    """Apply explicit wiring/state only. No chip models or guessed pin levels."""
    allowed = ("name", "description", "sources", "cpu_hz", "aliases", "pins",
               "i2c", "spi", "uart", "network")
    for key in profile:
        if key not in allowed:
            raise ValueError("unknown profile field: " + key)
    if "cpu_hz" in profile:
        mock_machine.freq(profile["cpu_hz"])
    mock_machine.Pin.configure_aliases(profile.get("aliases", {}))
    for configuration in profile.get("pins", ()):
        for key in configuration:
            if key not in ("id", "mode", "pull", "level"):
                raise ValueError("unknown pin field: " + key)
        pin = mock_machine.Pin(configuration["id"], **_pin_options(configuration))
        if "level" in configuration:
            pin.inject(configuration["level"])
    for kind, constructor, pin_fields in (
        ("i2c", mock_machine.I2C, ("sda", "scl")),
        ("spi", mock_machine.SPI, ("sck", "mosi", "miso")),
        ("uart", mock_machine.UART, ("tx", "rx", "rts", "cts")),
    ):
        for configuration in profile.get(kind, ()):
            options = dict(configuration)
            controller = options.pop("id")
            for field in pin_fields:
                if field in options and options[field] is not None:
                    options[field] = mock_machine.Pin(options[field])
            constructor(controller, **options)
    for configuration in profile.get("network", ()):
        for key in configuration:
            if key not in ("kind", "id", "active", "ifconfig", "connected", "status"):
                raise ValueError("unknown network field: " + key)
        kind = configuration["kind"]
        if kind == "LAN":
            interface = mock_network.LAN(id=configuration.get("id", 0))
        elif kind == "WLAN":
            interface = mock_network.WLAN(configuration.get("id", mock_network.STA_IF))
        else:
            raise ValueError("unsupported network kind: " + str(kind))
        interface.active(configuration.get("active", False))
        status = configuration.get("status")
        if isinstance(status, str):
            if not status.startswith("STAT_"):
                raise ValueError("network status must name a STAT_ constant")
            status = getattr(mock_network, status)
        interface.set_link(configuration.get("connected", False),
                           ifconfig=configuration.get("ifconfig"), status=status)


def run_application(filename, arguments=(), profile=None):
    """Install HAL before app imports, run as __main__, then restore interpreter.

    New application imports are removed at session end so a subsequent session
    cannot reuse modules retaining old machine/network handles. Existing modules
    (including native time/gc/os/framebuf) are never replaced or reloaded.
    Application exceptions and SystemExit are deliberately not swallowed.
    """
    global current_profile
    previous_profile = current_profile
    previous_modules = dict(sys.modules)
    previous_argv = sys.argv[:]
    previous_path = sys.path[:]
    previous_directory = os.getcwd()
    if not filename.startswith("/"):
        filename = previous_directory + "/" + filename
    slash = filename.rfind("/")
    directory = filename[:slash] or "/"
    try:
        mock_machine.reset_simulation()
        mock_network.reset_simulation()
        mock_machine.register_as_machine()
        mock_network.register_as_network()
        current_profile = {} if profile is None else profile
        apply_profile(current_profile)
        # MicroPython module objects have no public constructor. Import a fresh
        # private namespace so `import __main__` sees the executing script too.
        sys.modules.pop("_application", None)
        sys.path.insert(0, __file__[:__file__.rfind("/")])
        application = __import__("_application")
        sys.path.pop(0)
        sys.modules.pop("_application")
        namespace = application.__dict__
        namespace.update({"__name__": "__main__", "__file__": filename,
                          "__package__": None})
        sys.modules["__main__"] = application
        sys.argv[:] = [filename] + list(arguments)
        sys.path.insert(0, directory)
        os.chdir(directory)
        with open(filename) as source:
            code = source.read()
        exec(compile(code, filename, "exec"), namespace)
    finally:
        try:
            mock_machine.reset_simulation()
        finally:
            mock_network.reset_simulation()
            current_profile = previous_profile
            sys.argv[:] = previous_argv
            sys.path[:] = previous_path
            os.chdir(previous_directory)
            for name in tuple(sys.modules):
                if name not in previous_modules:
                    del sys.modules[name]
            for name, module in previous_modules.items():
                sys.modules[name] = module
