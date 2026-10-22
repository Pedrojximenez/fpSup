# Persistent camera-side loop design

## Goal

Replace the four unrolled AutoRun exchanges with one bounded, event-driven USB
worker. Preserve the verified v29 endpoint setup and framing, while avoiding
the blocking cache and teardown calls that caused hard locks.

```text
BOOT -> ENUM_WAIT -> READY -> ARM_OUT -> RX_VALIDATE -> DISPATCH
                                      ^                  |
                                      |                  v
                                WAIT_NEXT <- ARM_IN <- TX_REPLY
```

`CLOSE`, disconnect, timeout, or an internal fault enters a bounded cleanup
path. Cleanup must never wait indefinitely for an endpoint or callback.

## Verified anchors from v29

- EndTransfer: `0xC01E6D49`
- StartTransfer: `0xC01E6B81`
- EP05 OUT parameter: 10; EP84 IN parameter: 9
- context-4 mode address: `0xC31E38C8`; restore mode 2 after registration and
  before initialization
- DMA pointer: `[0xC3757A7C]`
- TRB tables: `[0xC31E3274]` and `[0xC31E3278]`
- CPU aliases `0x44` / `0xC4` have behaved coherently enough for echo
- Explicit cache invalidation and `FUN_c000ea54` have caused hard locks and are
  excluded from the baseline

## State rules

1. Only one OUT and one IN operation may be armed at a time.
2. Completion callbacks advance state; the worker must not spin or block the UI
   task waiting for USB.
3. Validate magic, version, length, CRC, and monotonic sequence before dispatch.
4. Replies retain request command and sequence and carry a status code.
5. Disconnect cancels pending work with a finite deadline, restores only state
   whose ownership is proven, and then releases the worker.
6. A watchdog records the last state and exits the experiment instead of
   repeatedly invoking uncertain teardown routines.

## Incremental implementation

1. Run a bounded 16-request echo diagnostic and record completion state after
   every request.
2. Repeat at 64 requests, including unplug/replug between idle requests.
3. Add `INFO` and explicit `CLOSE`; confirm normal camera shutdown both with and
   without the cable attached.
4. Only after shutdown is repeatable, remove the artificial request bound.
5. Add read-only operations with address/length allowlists. Memory writes and
   arbitrary calls remain out of scope until recovery and authorization rules
   are designed.

AutoRun itself has not shown a reliable loop/goto primitive, so a true long-lived
implementation likely requires a firmware task or callback-driven state object.
Do not guess a task-creation ABI in a production AutoRun; first recover it from
known firmware call sites and validate stack size, lifetime, and cancellation.
