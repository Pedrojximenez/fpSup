# Strict ARM ELF text extraction for offline probes

`load_text(path_or_bytes)` returns immutable `.text` bytes and named function
offsets, retaining each ARM ELF Thumb bit. This is not a linker, installer or
instruction/ABI verifier.

Only ELF32 little-endian ARM EABI5 ET_REL with one nonempty executable `.text`
is accepted. Unknown section types, writable allocated sections, additional
executable sections, undefined symbols, text relocations, malformed symbol/
relocation tables and overlapping/out-of-bounds sections are rejected. Unloaded
metadata is validated, not mapped; no relocation is applied. Caller must place
text at a suitably aligned address and independently bound execution.

Run `python3 -B test_elf_text.py`: 20 cases compile small ARM objects with
clang or mutate bounded object fixtures. All pass; no firmware/device/network
access is used. A successful extraction alone is not proof of safe execution.
