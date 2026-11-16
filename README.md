# KinCony simulation foundation

A reusable **Unix simulation foundation**, not N30/CO16 application bring-up.
The launcher runs a supplied MicroPython script with modeled `machine` and
`network` modules and a real native framebuffer. No custom firmware/image build,
host Python, pip, Node, compose, or other host tool installation is needed.
Runtime prerequisites are Linux, a working Docker CLI/daemon, a POSIX shell and
ordinary Linux utilities (`sha256sum`, `id`, `mktemp`, etc.).
The pinned image and verification target are Linux/amd64.

## Run

```sh
git clone https://github.com/mattytrentini/kincony-sim.git
cd kincony-sim
```

Then prepare the pinned runtime dependencies:

```sh
./sim prepare
./sim doctor
./sim doctor --profile n30
./sim doctor --profile co16
./sim run --name experiment examples/diagnostic.py
./sim run --name supplied --profile generic /absolute/path/to/main.py 'argument with spaces'
```

`prepare` is the **only networked dependency-install step**. It explicitly pulls
and uses this published image, with no Dockerfile or local image build:

```text
micropython/unix:v1.29.0@sha256:a176e29293235bc69829edd0e37be68ab77d18fc2b2817cd8cabed3ac564e8fb
```

`dependencies.json` is a deps-only mip manifest, pinning real full Git revisions.
Preparation runs the image's `mip` into a fresh staging directory, verifies
required imports/APIs, native-framebuffer integration and viewer assets, then
publishes `.cache/<full-manifest-sha256>/`. Failed preparation never marks a cache
ready. Changing the manifest requires a fresh explicit `./sim prepare`. A missing
cache/image produces an actionable error; `run`, `doctor`, and `test` never
install, download, pull, or retry. Re-running `prepare` reuses a completed cache.
Delete only the relevant `.cache/<hash>` directory to deliberately refresh it.

Applications run as scripts, with `__name__ == '__main__'`, their arguments in
`sys.argv`, their directory as the working directory and first import path, and
sibling imports supported. The application directory is mounted read-only at
`/app`; use `/tmp` for disposable output. Extra files outside the application
directory are not implicitly mounted. Exceptions/nonzero `SystemExit` propagate
through Docker to the shell. There are no fake board launcher applications.

## Isolation and ports

Every run has a separate interpreter, 8 MiB interpreter heap, named container,
read-only root/sources/dependencies and disposable `/tmp`. Containers run as the
calling UID/GID with `--init`, dropped capabilities, no-new-privileges, bounded
memory/process count, no privileged mode and **no passed-through host devices**.
No Docker socket, USB, serial devices, host networking, or `/lib` mount is used.
Docker's ordinary virtual `/dev` entries remain; this is not a sandbox for
untrusted application code.

Two instances can coexist without sharing modeled state:

```sh
./sim run --name first --profile n30 examples/diagnostic.py 15 &
./sim run --name second --profile co16 examples/diagnostic.py 15 &
wait
```

Container names are `kincony-sim-<name>`; a duplicate live name fails instead of
attaching to or restarting another instance. Names label instances, not boards.
Stop an instance with Ctrl-C or `docker stop kincony-sim-first`.

No host ports are published unless explicitly requested. Port syntax is numeric
`HOST:CONTAINER`, always bound to **127.0.0.1**, never all host interfaces:

```sh
./sim run --name display --port 8080:8080 examples/display.py
# Open http://127.0.0.1:8080/ on this Docker host.
```

The example draws with native `framebuf`, then uses the published
[framebuf_canvas](https://github.com/mattytrentini/framebuf_canvas) display-only
viewer. It is not a simulation I/O-control panel. Services must listen on
`0.0.0.0` **inside** the container to receive a published port. Docker bridge
networking and native Unix sockets/DNS remain real: simulated LAN/WLAN link state
neither configures nor gates socket traffic, does not join Wi-Fi, and does not
assign the modeled addresses to real interfaces. Outbound networking is possible
through Docker's ordinary bridge.

## Profiles, not peripheral models

Select `generic`, `n30`, `co16`, or a JSON file with `--profile FILE`. The bootstrap
installs both HAL modules **before application imports**, resets their registries,
applies explicit configuration, and resets again on exit. It restores prior
module entries, import path, argv and working directory, removing new application
imports so successive in-process sessions do not reuse stale HAL references.
Native `time`, `gc`, `os`, `framebuf`, `asyncio`, and `micropython` remain native;
there is no fake `os.uname()` or ESP32 interpreter identity.
The stock image does not expose `os.uname()`; diagnostics use `sys.platform`.
Board applications that expect ESP32 identity APIs need an explicit identity
boundary during their later bring-up, not a fake replacement `os` module.

Supported profile fields:

- `name`, `description`, `sources`: descriptive metadata.
- `cpu_hz`: positive virtual CPU-frequency metadata, never host CPU control.
- `aliases`: one-level Pin name to canonical integer/string ID mapping.
- `pins`: entries with `id` and optional `mode` (`IN`, `OUT`, `OPEN_DRAIN`),
  `pull` (`PULL_UP`, `PULL_DOWN`, or null), and injected sampled `level` (0/1/null).
- `i2c`, `spi`, `uart`: controller entries with `id` plus supported constructor
  options. Pin-valued options resolve through the configured Pin identities.
  Configuration attaches **no device** and fabricates no response.
- `network`: `kind` (`LAN`/`WLAN`), `id`, `active`, `connected`, optional four-entry
  IPv4 `ifconfig`, and optional numeric/named `STAT_...` status. A positive modeled
  link requires activation and an explicitly configured nonzero address.

The synthetic `generic` profile supplies a demonstration input and documentation
address. N30/CO16 profiles copy aliases and bus wiring from these authoritative
board definitions:

- `kincony-n30/boards/KINCONY_N30/{pins.csv,mpconfigboard.h,mpconfigboard.cmake}`
- `kincony-co16/ports/esp32/boards/KINCONY_CO16/{pins.csv,mpconfigboard.h,mpconfigboard.cmake}`

Both board CMake files select `sdkconfig.240mhz`. Profile CPU values are only
metadata. Board profiles do **not** invent pin levels, pullups, default output
drives, attached chips, or successful bus transactions. Their distinct
`192.0.2.30` / `192.0.2.16` link addresses are explicit simulation settings, not
hardware facts or real DHCP results. Shared/overlapping aliases intentionally
refer to the same canonical GPIO; this does not model electrical conflicts or
arbitrate optional peripherals.

`WLAN.connect(ssid, password)` records a pending association and reports
`STAT_CONNECTING`; it never associates automatically. A model explicitly calls
`interface.set_link(True, ifconfig=(address, mask, gateway, dns))` to complete the
transition, or supplies a failure status with `set_link(False, status=...)`.
`disconnect()` and deactivation drop the connection; static configuration is
retained. Diagnostic snapshots contain no SSIDs/passwords. Reset deactivates old
handles and clears interface identities/configuration.

The diagnostic demonstrates Pin aliases/configuration/real scheduled IRQ edges,
generic I2C register storage, a bounded UART responder, native framebuffer
pixels, and explicit network transitions with actual assertions and outputs.
It creates only clearly synthetic test devices, not a W5500, RTC, relay expander,
meter coprocessor, or display-controller emulator.

**Not implemented:** N30/CO16 chip models or application startup, board I/O web
control, electrical timing/contention/calibration, physical networking, hardware
validation, native ESP32-only modules, or arbitrary firmware compatibility.

## Tests and development

After preparation, run explicitly:

```sh
./sim test
./tests/cli.sh
```

The first executes deterministic behavioral tests in the pinned stock image:
bootstrap import ordering, arguments/sibling imports, native-module retention,
cleanup on success/failure/SystemExit, profile isolation without fake devices,
network transitions/atomic failures/reset, and the generic diagnostic. The
host-side CLI checks missing preparation, application exit/error propagation,
rejection of public-address port syntax, and two concurrent real interpreters
with read-only mounts and no exposed devices. It uses unique test instance names
and cleans up only its own containers.

`lib/framebuf_canvas` and `lib/mock_machine` are Git submodules pinned as source
and development references. Default runtime imports are **mip-installed** from
the manifest cache, not these source trees. When updating dependencies: publish
the library commit first, then update both the full manifest SHA and matching
submodule revision, then explicitly prepare and test. Do not replace immutable
revisions with branch names or vendor copies. Developers who need source
checkouts can use `git submodule update --init --recursive`; Git is not a runtime
package installer.

The mock library's upstream `Makefile` discovers `test/test_*.py` using
`unittest_junit` in MicroPython; its new `test/test_mock_network.py` follows that
layout. The runtime's own checks need no additional unittest installation.

## Verification

Verified with the unchanged pinned Unix image: native mock/driver regression
suites, six runtime contract groups, application exit/error propagation,
concurrent N30/CO16 configuration sessions, read-only mounts and no exposed
host devices. The display example was opened in a real browser and its native
128×64 Canvas pixels checked.

## License

MIT; see `LICENSE`. The reused framebuf_canvas, Microdot and
micropython-mock-machine libraries are MIT-licensed, with attribution/licenses
retained in the mip installation. The mock library also pins its official
micropython-lib logging dependency rather than fetching an unversioned latest.
