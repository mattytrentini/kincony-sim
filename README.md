# KinCony Unix simulator

Run the **real N30 and CO16 applications**, web dashboards and display drawing
on an unchanged published MicroPython Unix image. Reusable digital peripheral
models provide actual driver-level GPIO, I2C, UART and SPI transactions.
The foundation also runs supplied scripts without board-specific chip models.
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
git submodule update --init lib/kincony_n30 lib/kincony_co16
./sim prepare
./sim n30
# Or launch the CO16 instead, on host port 8081:
# ./sim co16
```

Open these on the Docker host:

| URL | Surface |
| --- | --- |
| http://127.0.0.1:8080/ | Original N30 dashboard and GPIO15/16 output controls |
| http://127.0.0.1:8080/display/ | Live OLED Canvas over WebSocket |
| http://127.0.0.1:8080/sim/ | Synthetic inputs, all 30 currents, voltage/frequency and communication faults |
| http://127.0.0.1:8081/ | Original CO16 dashboard, 16 relay controls and clock readback |
| http://127.0.0.1:8081/display/ | Live 320×240 RGB565 LCD Canvas over WebSocket |
| http://127.0.0.1:8081/sim/ | 16 digital input stimuli, register/RTC flags and per-device faults |

For another instance/host port:

```sh
./sim n30 --name bench --port 8090:8080
./sim co16 --name co16-bench --port 8091:8080
```

Stop with Ctrl-C or `docker stop kincony-sim-n30` (or `kincony-sim-bench`).
State is disposable: a fresh process starts GPIO15/16 as inputs without pulls
or saved output commands, and restores the explicit synthetic meter defaults.
No hardware devices are accessed or passed through.
CO16 uses container name `kincony-sim-co16`; stop it with Ctrl-C or
`docker stop kincony-sim-co16`. N30 and CO16 can run simultaneously at their
different default host ports. A fresh CO16 starts with relay latch `0xffff`
(all signals OFF), all digital inputs idle, input configuration `0xffff`,
polarity zero and all devices online. The explicit synthetic RTC starts at
2026-01-01 00:00:00, OSF clear; it is not a hardware or host clock reading.

### N30 simulation controls

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

### CO16 simulation controls

Launch with **`./sim co16`**. The original application at `/` owns all relay
commands and clock setting; `/sim/` only supplies environmental stimuli.
No second CO16 provider, output bank or browser-ticking clock is substituted.

- Stage any of 16 active-low external inputs, then Apply atomically. Advanced
  input configuration/polarity are explicit register stimuli. A non-all-input
  configuration makes the real application return `503`; neither app nor panel
  silently repairs it. Decoded polarity handling uses the original XL9535 driver.
- Relay readback is the real PCF8575 sampled control port, **not contact feedback**.
  Use the original dashboard for relay commands; each actual driver write
  preserves unrelated channel bits. Startup/LCD/GETs perform no I2C control writes.
- The real DS3231 driver reads a ticking, timezone-naive BCD calendar. Toggle OSF
  to test untrusted time; set time through the original clock REST API. That actual
  register write clears OSF while preserving unrelated status bits. Reads do not
  set time or clear flags.

  ```sh
  curl -X POST http://127.0.0.1:8081/api/v1/time \
    -H 'Content-Type: application/json' -d '{"datetime":"2028-02-29T12:34:56"}'
  ```
- Per-device online controls inject I2C/SPI `EIO`, not zeros. I2C restoration
  recovers the real read paths. A fatal LCD SPI error stops the original drawing
  task but not HTTP. Restoring LCD online **does not restart it**; restart the
  process. A connected Canvas can retain its last frame; worker status warns.
- The unchanged ST7789 driver, CO16 bus configuration and ROM font generate the
  actual splash/status/error pixel stream. Generic SPI/Pin observers model the
  controller; a 40ms publisher pump coalesces dirty drawing bursts before taking
  RGB565 snapshots. This is a logical pixel view, not a physical-panel photograph.

CO16 simulation JSON routes: `GET /sim/api/state`, `POST /sim/api/inputs`
with any nonempty subset of `active` (16 strict booleans), `config` and `polarity`
(unsigned 16-bit integers), `POST /sim/api/rtc` with `{"osf":boolean}`, and
`POST /sim/api/devices/<relays|inputs|rtc|lcd>` with `{"online":boolean}`.
Validation is atomic; responses are no-store. Model metadata/environment settings
remain distinct from actual decoded reads and independent unavailable resources.
These unauthenticated controls are for host loopback, not the Internet.

The existing CO16 application does not initialize its ADS1115 ADCs, EEPROM or
optional modules, so these are not invented by the simulator.

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
cache/image produces an actionable error; board runs, generic runs, diagnostics
and tests never install, download, pull or retry. `prepare` reuses a completed cache.
Delete only the relevant `.cache/<hash>` directory to deliberately refresh it.

Applications run as scripts, with `__name__ == '__main__'`, their arguments in
`sys.argv`, their directory as the working directory and first import path, and
sibling imports supported. The application directory is mounted read-only at
`/app`; use `/tmp` for disposable output. Extra files outside the application
directory are not implicitly mounted. Exceptions/nonzero `SystemExit` propagate
through Docker to the shell. Board startup composes each original application,
not a high-level substitute board implementation.

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

Generic runs publish no host ports unless requested. N30 defaults to
`8080:8080`, CO16 to `8081:8080`. Numeric `HOST:CONTAINER` mappings always bind
to **127.0.0.1**:

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
Both boards accept an explicit `identity_provider`; CO16 reports the native Unix
MicroPython release, not an ESP32 identity. Hardware keeps native `os.uname()`;
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

**Not implemented:** ADC/EEPROM/optional LoRa, SD, PT100, KNX or other peripheral
models, electrical timing/contention/calibration, physical networking, hardware
validation, native ESP32-only modules, or arbitrary firmware compatibility.

## Tests and development

After preparation, run explicitly:

```sh
./sim test
./sim test-n30
./sim test-co16
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

`test-co16` exercises the original app over real TCP: all sixteen relay bits and
inputs, unrelated-bit preservation, polarity/configuration, independent I2C
faults and recovery, readonly RTC/OSF and ticking leap midnight, actual RGB565
LCD states, HTTP during the splash, safe clean restart and HTTP survival after
a fatal display error. No hardware, host-published test ports or unittest package
are required by these application scenarios.

`lib/kincony_n30` and `lib/kincony_co16` are the pinned **runtime application
sources**; initialize them as shown above. Their hardware manifests install
`../main.py` and flat Microdot, so they are not used for simulation. Actual
SSD1306/umodbus and PCF8575/XL9535/DS3231/ST7789/config/font drivers are separately
mip-installed at the same immutable pins used by the respective board projects.

`lib/framebuf_canvas`, `lib/mock_machine` and `lib/sim_devices` are pinned library
source/development references; runtime imports use **mip-installed** cache copies,
not these library checkouts. Publish tested library changes before updating
manifest/submodule SHAs, then explicitly prepare and test. Never use branch-name
runtime pins or vendor driver replacements. For all development references use
`git submodule update --init --recursive`; nested firmware trees are not needed
to run either application.

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

CO16 verification passed 25 new model/unchanged-driver tests plus 24 HAL/network
contracts, and three real HTTP application sessions. These covered all relay
and input channels, zero startup/GET control writes, fault recovery, leap-midnight
RTC ticking, actual RGB565 LCD states, safe restart and HTTP survival after
fatal LCD failure. Browser checks covered cross-page relay/input control,
OSF and I2C faults, dirty-form preservation, pixel-checksum parity and desktop/
390px mobile rendering without page overflow. Hardware remained untouched.

## License

Own framework/application-integration/model code is MIT; see `LICENSE`.
framebuf_canvas, Microdot, micropython-mock-machine and the selected SSD1306,
PCF8575, XL9535, DS3231 and ST7789/config/font drivers are MIT-licensed, with
their original notices retained in the prepared installation.
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
