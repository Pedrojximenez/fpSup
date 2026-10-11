# FPShell 1.0

`fpshelld` is the sole owner of the SIGMA fp vendor USB interface. Local
programs and multiple agents use its permission-restricted Unix socket, so
EP05 OUT and EP84 IN transactions cannot be interleaved by competing libusb
processes.

```text
agents / scripts -> fpshell -> /tmp/fpshell.sock -> fpshelld -> EP05 / EP84
```

The production baseline uses the verified v29 timing: claim interface 1, wait
32 seconds, then send at most four framed transactions. The 64-byte `FPSH` frame adds protocol
version, command, sequence, length, status, and CRC32 validation even though
the present AutoRun only echoes it. See `PROTOCOL.md` for the wire layout.

## Build and self-test

```sh
make clean all
make test
make package
```

The tests use `--mock`; they do not need a camera or consume an AutoRun round.
They cover framing, request limits, concurrent clients, single-daemon ownership,
socket permissions, JSON output, Unicode byte limits, and clean shutdown.

## Mock mode

```sh
./fpshelld --mock --limit 4
./fpshell status
./fpshell ping
./fpshell echo hello
./fpshell --json status
./fpshell quit
```

## Camera mode

Copy `dist/AutoRun.txt` to the root of the 16GB ExFAT camera card. The compact
AutoRun performs no diagnostic file writes: one flash means it started, two
flashes mean connect USB, and three flashes mean its four-round session ended.

Boot the camera, connect USB immediately after the second flash, then run:

```sh
./fpshellctl start                 # backgrounds daemon; waits until fully ready
./fpshell status                   # local only; does not consume a request
./fpshell echo "hello fp"          # consumes one camera request
./fpshell ping                     # consumes one camera request
./fpshellctl stop
```

Options:

- `fpshelld --arm-wait SEC --inter-wait-ms MS --limit N --socket PATH`
- `fpshell --socket PATH --timeout SEC --json COMMAND`
- `fpshellctl [--json] start|status|stop`
- `FPSHELL_SOCKET` changes the default socket for both processes.

`fpshellctl start` does not publish the service socket until the USB transport
is ready. A separate advisory lock prevents a second daemon from racing for the
camera during discovery or the 32-second arm wait. Its default 2500 ms
inter-request guard lets the compact AutoRun retire one round and arm the next
before another client can submit USB traffic. Logs are written beside the
socket (normally `/tmp/fpshell.sock.log`).

`make package` creates a self-contained macOS arm64 archive under `release/`,
including libusb, the compact AutoRun, documentation, and a SHA-256 manifest.

Exit codes are 0 for `OK`, 1 for a daemon/camera `ERR`, and 2 for local usage,
connection, or timeout errors. `--json` emits one compact JSON object, which is
the recommended interface for agents.

## Current safety boundary

- Camera execution is a bounded framed transport, currently echo-only; there are no memory-write or arbitrary
  call commands.
- One camera boot currently supports four USB exchanges. Restarting only the
  daemon does not re-arm the camera AutoRun.
- The known post-traffic shutdown hang is unresolved. This tool therefore does
  not claim to perform safe camera teardown. If the camera hangs, disconnect
  USB and remove the battery for 20–30 seconds before retrying.
- v31–v33 teardown experiments are research artifacts, not this stable branch.

The intentionally bounded design is the final stable baseline for this project.
`CAMERA_LOOP_DESIGN.md` preserves the future persistent-loop design, but it is
not part of FPShell 1.0.
