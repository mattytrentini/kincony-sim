#!/bin/sh
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini
# Host-side Docker integration checks. Run explicitly after ./sim prepare.
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
SCRATCH=$(mktemp -d)
PREFIX="contract-$$"
FIRST=
SECOND=
cleanup() {
    if [ -n "$FIRST" ]; then
        docker rm -f "kincony-sim-$PREFIX-n30" >/dev/null 2>&1 || :
        kill "$FIRST" 2>/dev/null || :
    fi
    if [ -n "$SECOND" ]; then
        docker rm -f "kincony-sim-$PREFIX-co16" >/dev/null 2>&1 || :
        kill "$SECOND" 2>/dev/null || :
    fi
    rm -rf -- "$SCRATCH"
}
trap cleanup EXIT HUP INT TERM

wait_ready() {
    LOG=$1
    PID=$2
    COUNT=0
    until [ -f "$LOG" ] && grep -q 'diagnostic complete' "$LOG"; do
        if ! kill -0 "$PID" 2>/dev/null || [ "$COUNT" -ge 400 ]; then
            cat "$LOG" >&2
            printf '%s\n' 'FAIL instance did not reach diagnostic readiness' >&2
            return 1
        fi
        COUNT=$((COUNT + 1))
        sleep 0.05
    done
}

# The missing-prepare path must fail before attempting to pull or run anything.
mkdir "$SCRATCH/unprepared"
cp "$ROOT/sim" "$ROOT/dependencies.json" "$SCRATCH/unprepared/"
if "$SCRATCH/unprepared/sim" run "$ROOT/tests/fixtures/exit.py" >"$SCRATCH/missing.log" 2>&1; then
    printf '%s\n' 'FAIL missing preparation was accepted' >&2
    exit 1
else
    STATUS=$?
    [ "$STATUS" -eq 2 ]
    grep -q 'run ./sim prepare' "$SCRATCH/missing.log"
fi
# Failures must be the application's status, not launcher success.
if "$ROOT/sim" run --name "$PREFIX-exit" "$ROOT/tests/fixtures/exit.py" >"$SCRATCH/exit.log" 2>&1; then
    printf '%s\n' 'FAIL application SystemExit was swallowed' >&2
    exit 1
else
    STATUS=$?
    [ "$STATUS" -eq 23 ]
fi
if "$ROOT/sim" run --name "$PREFIX-error" "$ROOT/tests/fixtures/failure.py" >"$SCRATCH/error.log" 2>&1; then
    printf '%s\n' 'FAIL application exception was swallowed' >&2
    exit 1
else
    grep -q 'application failure must escape' "$SCRATCH/error.log"
fi
if "$ROOT/sim" run --port 0.0.0.0:8080:8080 "$ROOT/examples/display.py" >"$SCRATCH/port.log" 2>&1; then
    printf '%s\n' 'FAIL non-loopback port syntax was accepted' >&2
    exit 1
fi

# Keep both actual interpreters alive until explicitly released over stdin.
mkfifo "$SCRATCH/n30.in" "$SCRATCH/co16.in"
exec 3<>"$SCRATCH/n30.in"
exec 4<>"$SCRATCH/co16.in"
"$ROOT/sim" run --name "$PREFIX-n30" --profile n30 "$ROOT/examples/diagnostic.py" wait <&3 >"$SCRATCH/n30.log" 2>&1 &
FIRST=$!
"$ROOT/sim" run --name "$PREFIX-co16" --profile co16 "$ROOT/examples/diagnostic.py" wait <&4 >"$SCRATCH/co16.log" 2>&1 &
SECOND=$!
wait_ready "$SCRATCH/n30.log" "$FIRST"
wait_ready "$SCRATCH/co16.log" "$SECOND"
for INSTANCE in "$PREFIX-n30" "$PREFIX-co16"; do
    FLAGS=$(docker inspect --format '{{.State.Running}} {{.HostConfig.Privileged}} {{.HostConfig.ReadonlyRootfs}} {{len .HostConfig.Devices}} {{len .HostConfig.DeviceRequests}} {{len .HostConfig.PortBindings}}' "kincony-sim-$INSTANCE")
    [ "$FLAGS" = 'true false true 0 0 0' ]
    MOUNTS=$(docker inspect --format '{{range .Mounts}}{{if eq .Type "bind"}}{{.RW}} {{end}}{{end}}' "kincony-sim-$INSTANCE")
    case "$MOUNTS" in *true*) printf '%s\n' 'FAIL writable host mount' >&2; exit 1 ;; esac
done
printf '\n' >&3
printf '\n' >&4
exec 3>&-
exec 4>&-
wait "$FIRST"
FIRST=
wait "$SECOND"
SECOND=
grep -q '192.0.2.30' "$SCRATCH/n30.log"
grep -q '192.0.2.16' "$SCRATCH/co16.log"
grep -q 'diagnostic complete' "$SCRATCH/n30.log"
grep -q 'diagnostic complete' "$SCRATCH/co16.log"
printf '%s\n' 'PASS Docker launcher failures, missing prepare and concurrent no-device isolation'
