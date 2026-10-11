# EP83 noncached pool mapping guard

Scope: offline ROM/source audit and implementation; no device memory read or write.
ROM SHA-256: `aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.

`highrate/af_ep83_memory.c` now checks the live ARM MMU configuration rather than
inferring an uncached alias from the existing worker. This is a mapping predicate,
not an exclusive allocation lease or a cold-boot installer.

## Independent native evidence

- `C03FA3E8` implements `memmgr bufmem`: type 0 resolves through `C001CF78` and
  `C001CFD8`. Its implementation and assertion strings identify NonCacheBuf.
  The result at `C3757A7C` is `{address, actual_size, allocator_type}`. Boot allocation
  uses three arguments `get 0 1048576`; a fourth argument overwrites the size.
- `C01E5320` bulk IN, including its direct normal-TRB branch, converts a CPU address
  in the noncached `0x4...` allocation class to USB bus by subtracting `0x40000000`.
  This USB-bus conversion is NOT the same operation as an ARM MMU translation.
- `C000E7B0` initializes the MMU. Literal `C000EBF8 = 44300000` names its table;
  its final TTBR0 is `44300040` and DACR is `55555555`.
- Default table row at `C0725F60` is `{40000000, 800, 3, 0, 00400000}`.
  The code emits repeated 16 MB supersection entries. For CPU `44xxxxxx`, all 16
  entries must equal `44044C02`: physical `44000000`, privileged/user RW, normal
  inner/outer noncached, not execute-never. The `C...` region has different cache
  attributes and is not accepted by this guard.
- Boot can select another mapping table through `C2EF6F60/64`. Therefore checking
  the ROM default alone is insufficient: the guard reads the actual active table.

## Implemented checks

The ARM callback reads SCTLR, TTBCR, TTBR0 and DACR without modifying them. It requires
MMU enabled, no TEX remap, little endian, unsplit short descriptors, the exact known
TTBR and domain setup. Only then may it read the known table at `44300000`.
It checks every entry in the first and last supersection covering pool offsets
`0..64FFF`. All descriptors must match the expected noncached physical mapping.

The allocation descriptor must match the expected 64-byte-aligned pool base, type 0,
and at least 1 MiB without wrapping out of the `40000000..7FFFFFFF` region. The active
lease itself uses `50000..64FFF`; no `+40000000` CPU alias is used. Code/state/records/
DMA and metadata have nonoverlapping subranges checked by their respective builders.

`af_ep83_build_identity_ok` checks the complete 40-byte build label
`13aa621060efff11aaba9b21ad925005302605cf` and its NUL at `C0725F94`. It is a runtime
build-label check, not a hash of the full running image or proof of unchanged patches.

## Limits

These predicates do not allocate memory, hold an owner lock, exclude other payloads,
prove the pool will not be freed later, or establish endpoint/DMA completion. They
must be combined with a dedicated cold-boot image, no legacy worker/other loader,
an explicit one-shot ownership/lifecycle, and the completion receipt. Non-ARM builds
of both hardware callbacks return false. Six host tests cover the pure predicate,
all table words, unsupported register modes, allocation bounds and ROM constants.
