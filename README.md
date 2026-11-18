# KinCony Unix simulator

Run the **real N30 application**, web dashboard, native OLED drawing and metering
decoder on an unchanged published MicroPython Unix image. Reusable digital
peripheral models supply GPIO, SSD1306 I2C and ARM Modbus RTU responses.
The foundation also runs supplied scripts; CO16 remains a wiring-only profile.
No custom firmware/image build, host Python, pip, Node or Compose is needed.
Runtime prerequisites are Linux, a working Docker CLI/daemon, a POSIX shell and
ordinary Linux utilities (`sha256sum`, `id`, `mktemp`, etc.).
The pinned image and verification target are Linux/amd64.

## Run

```sh
git clone https://github.com/mattytrentini/kincony-sim.git
cd kincony-sim
```

Initialize the pinned application source, prepare libraries once, then launch:

```sh
git submodule update --init lib/kincony_n30
./sim prepare
./sim n30
```

Open these on the Docker host:

| URL | Surface |
| --- | --- |
| http://127.0.0.1:8080/ | Original N30 dashboard and GPIO15/16 output controls |
| http://127.0.0.1:8080/display/ | Live OLED Canvas over WebSocket |
| http://127.0.0.1:8080/sim/ | Synthetic inputs, all 30 currents, voltage/frequency and communication faults |

For another instance/host port:

```sh
./sim n30 --name bench --port 8090:8080
```

Stop with Ctrl-C or `docker stop kincony-sim-n30` (or `kincony-sim-bench`).
State is disposable: a fresh process starts GPIO15/16 as inputs without pulls
or saved output commands, and restores the explicit synthetic meter defaults.
No hardware devices are accessed or passed through.

### Simulation controls

`/sim/` distinguishes **staged edits**, applied environmental inputs, and the
real application's cached decoded observations. Saves are explicit and atomic;
polling does not overwrite dirty forms. Decoder updates follow the original
five-second bank polling cycle; injected values are never copied into its cache.

- Inject low/high/release into GPIO0, GPIO8, GPIO15 or GPIO16 while inputs.
  Outputs are read-only here: change their mode/level in the original dashboard.
  Injection into an output returns `409`, rather than overriding it. A released
  sampled level is unknown, not zero; this is not an electrical circuit model.
- Each of three banks has ten current inputs, voltage/frequency, and
  `normal`, `timeout` or `crc` response mode. Timeout drops the actual UART
  response; CRC corrupts its checksum. The original driver rejects both and
  reports unavailable values, **not zero**. Other banks continue polling.
- Defaults are explicitly synthetic: **0 A, 230 V, 50 Hz**, not measured values.
  Current resolution is 0.001 A, voltage/frequency 0.01. Validation limits follow
  register representability (uint32 milliamps, uint16 voltage/frequency hundredths),
  not physical CT ratings or calibration. Unknown power/energy/temperature slots
  are zero-filled raw registers, not implemented measurements.
- The unchanged SSD1306 driver draws the original snake splash and rotating
  system/network pages with native `framebuf`. The I2C model mirrors its logical
  pixels to reusable `framebuf_canvas`; there is no duplicate OLED renderer.
  Unix heap/filesystem/uptime are real; CPU frequency, LAN identity and addresses
  are explicitly modeled metadata, not host configuration.

Simulation-only JSON endpoints are `GET /sim/api/state`,
`POST /sim/api/inputs/<pin>` with `{\"level\":0|1|null}`, and
`POST /sim/api/banks/<bank>` with any nonempty subset of `currents_A` (ten numbers),
`voltage_V`, `frequency_Hz`, `fault`. Reads never apply inputs or trigger polling.
Invalid shapes, nonfinite/out-of-range values and unknown fields fail atomically.
Controls are unauthenticated and published only on host loopback; do not expose
them to the Internet.

### Supplied applications and diagnostics

```sh
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
cache/image produces an actionable error; `n30`, `run`, `doctor`, `test` and
`test-n30` never install, download, pull or retry. `prepare` reuses a completed cache.
Delete only the relevant `.cache/<hash>` directory to deliberately refresh it.

Applications run as scripts, with `__name__ == '__main__'`, their arguments in
`sys.argv`, their directory as the working directory and first import path, and
sibling imports supported. The application directory is mounted read-only at
`/app`; use `/tmp` for disposable output. Extra files outside the application
directory are not implicitly mounted. Exceptions/nonzero `SystemExit` propagate
through Docker to the shell. N30 startup composes the original board app, not a
high-level substitute board implementation.

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

Generic runs publish no host ports unless explicitly requested; `n30` defaults to
`8080:8080`. Port syntax is numeric `HOST:CONTAINER`, always bound to **127.0.0.1**:

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
N30 supplies an explicit `identity_provider` to its board constructor and stores
that identity for the OLED. Hardware keeps its default native `os.uname()` path;
no native `os`, `time`, `gc`, `framebuf` or networking sockets are replaced.

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

**Not implemented:** CO16 chip models/application startup, N30 LoRa/SD/EEPROM
models, electrical timing/contention/calibration, physical networking, hardware
validation, native ESP32-only modules, or arbitrary firmware compatibility.

## Tests and development

After preparation, run explicitly:

```sh
./sim test
./sim test-n30
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

`test-n30` uses real TCP against the original app and real worker lifecycle.
It covers shared GPIO input/output controls, blocked output injection, all thirty
decoded currents including uint32 word boundaries, per-bank voltage/frequency,
atomic invalid updates, actual UART timeout/CRC rejection and recovery,
unavailable-versus-zero semantics, live OLED refresh and a second clean session
after driven outputs and injected faults. It needs no hardware, published ports
or additional test package.

`lib/kincony_n30` is the pinned **runtime application source**; initialize it as
shown above. Its root hardware mip manifest deliberately installs `../main.py`
and flat Microdot, so it is not used for simulation. SSD1306 and the actual
umodbus client are separately mip-installed at the same immutable source pins
used by the board project.

`lib/framebuf_canvas`, `lib/mock_machine` and `lib/sim_devices` are pinned library
source/development references; runtime imports use **mip-installed** cache copies,
not these library checkouts. Publish tested library changes before updating
manifest/submodule SHAs, then explicitly prepare and test. Never use branch-name
runtime pins or vendor driver replacements. For all development references use
`git submodule update --init --recursive`; nested firmware trees are not needed
to run the N30 application.

The mock library's upstream `Makefile` discovers `test/test_*.py` using
`unittest_junit` in MicroPython; its new `test/test_mock_network.py` follows that
layout. The runtime's own checks need no additional unittest installation.

## Verification

Verified with the unchanged pinned Unix image: native mock/driver regression
suites, six runtime contract groups, application exit/error propagation,
concurrent N30/CO16 configuration sessions, read-only mounts and no exposed
host devices. The display example was opened in a real browser and its native
128×64 Canvas pixels checked.

N30 verification additionally passed 30 focused HAL/device/real-driver regression
tests and the two-session real HTTP application scenario. Browser checks covered
shared GPIO controls, dirty-form preservation, injected current decoded by the
real client, CRC failure/recovery and matching Canvas/controller pixel checksums.
The controls were visually checked at desktop and 390px mobile widths.
No physical board was accessed, flashed or used for these checks.

## License

Own framework/application-integration/model code is MIT; see `LICENSE`.
framebuf_canvas, Microdot, micropython-mock-machine and the official SSD1306
driver are MIT-licensed, with notices retained in the mip installation.
The mock library pins its official logging dependency rather than an unversioned
latest.

**Modbus licensing caveat:** the external micropython-modbus root license is
GPLv3 and source headers say GPLv3-or-later with permitted additional Pycom
terms, while its README claims MIT. Those additional terms remain unverified.
Do not treat this dependency or the combined application as MIT, or assume
external installation resolves redistribution obligations. Establish applicable
terms before product redistribution. No GPL client implementation is copied into
the independently implemented MIT protocol models. Exact upstream root notices
are retained under `licenses/` and copied into the prepared dependency cache;
original driver source notices remain intact.
