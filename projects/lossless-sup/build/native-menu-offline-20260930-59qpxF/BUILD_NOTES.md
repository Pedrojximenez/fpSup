# Lossless native menu offline build

2026-09-30. The permission resource, native variable port and ARM32 reader bridge
are implemented and tested offline. No installed menu, full-page rendering,
camera readiness, recording readiness or deployable BIN is claimed.
See `../../notes/PROGRESS_20260930.md` §11 for the current development path.

## Output and source identity

Work from `/Users/dido/Developer.localized/SIGMAfp_re`.
Output directory is `projects/lossless-sup/build/native-menu-offline-20260930-59qpxF`.
`SHA256SUMS` uses paths relative to that working directory. Check with
`shasum -a 256 -c projects/lossless-sup/build/native-menu-offline-20260930-59qpxF/SHA256SUMS`.
Artifacts are not written to a card or any previous build directory.

The input is `out/seg0_c0000000.bin`, 49245696 bytes, SHA-256
`aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622`.
Tools: Python 3.9.6, Apple clang 21.0.0, Unicorn 2.1.4.

Build each resource into a new directory (use a new output parent to reproduce):

```sh
python3 -B fpSup/lossless/menu/build_menu_candidate.py --seg0 out/seg0_c0000000.bin --audit-module research/ui/tools/native_ui_audit.py --profile native-permission-gated --output projects/lossless-sup/build/native-menu-offline-20260930-59qpxF/permission
python3 -B fpSup/lossless/menu/build_menu_candidate.py --seg0 out/seg0_c0000000.bin --audit-module research/ui/tools/native_ui_audit.py --output projects/lossless-sup/build/native-menu-offline-20260930-59qpxF/fixed
```

`permission/`: page 179907 B, pool 176300 B, 1541 records, 214 objects. Their
SHA-256 values are `e602a154162790287fed8a182e07fda0af5d02509b59300a25725fe923c71dea`
and `3ff3ea5264f8a16aec7fac30160cc8065dfe1d2b896fb7b40c3212de5cf7d3ba`.
`fixed/` reproduces the unchanged previous default resource.
Both manifests report `BLOCKED_NOT_DEPLOYABLE`.

Compile the three ARM objects:

```sh
for unit in native/native_variable native/native_port loader/native_reader; do
  clang --target=armv7-none-eabi -mcpu=cortex-a9 -mthumb -mfloat-abi=soft -mfpu=none -std=c11 -O2 -ffreestanding -fno-builtin -fno-addrsig -fno-unwind-tables -fno-asynchronous-unwind-tables -Wall -Wextra -Werror -IfpSup/lossless/binding -IfpSup/lossless -c fpSup/lossless/$unit.c -o projects/lossless-sup/build/native-menu-offline-20260930-59qpxF/$(basename "$unit").o
done
```

Object sizes: native_variable 4304 B, native_port 6132 B, native_reader 2784 B.
These are objects, not executable card payloads. native_port requires legitimate
relocation/linking of its rodata and function table; stripping relocations is
not a build solution. No linker, loader or AutoRun change is made here.

## Verified commands

Each command was run from the root above. Its full output is in the named log;
all returned zero with no skipped tests. See `ledger.json` for individual counts.

```sh
python3 -B -m unittest discover -s fpSup/lossless/native -p test_native_permissions.py -v
python3 -B fpSup/lossless/native/test_native_port.py
python3 -B -m unittest discover -s fpSup/lossless/binding -p 'test_*.py' -v
python3 -B -m unittest discover -s fpSup/lossless/tests -p 'test_*.py' -v
python3 -B fpSup/lossless/menu/test_permission_candidate.py --seg0 out/seg0_c0000000.bin --audit-module research/ui/tools/native_ui_audit.py
python3 -B fpSup/lossless/menu/test_menu_candidate.py --seg0 out/seg0_c0000000.bin --audit-module research/ui/tools/native_ui_audit.py
FPLOSSLESS_SEG0=out/seg0_c0000000.bin python3 -B fpSup/lossless/menu/test_recipe.py
python3 -B fpSup/lossless/native/test_native_variable.py --seg0 out/seg0_c0000000.bin --shared-probe research/ui/tools/native_variable_probe/binding_probe.py --elf-helper research/ui/tools/arm_text/elf_text.py
python3 -B research/ui/tools/native_control_probe/test_native_permission_binding.py --worker
python3 -B fpSup/lossless/loader/test_native_reader.py --seg0 out/seg0_c0000000.bin --candidate projects/lossless-sup/build/native-menu-offline-20260930-59qpxF/permission --profile native-permission-gated
python3 -B fpSup/lossless/loader/test_native_reader.py --seg0 out/seg0_c0000000.bin --candidate projects/lossless-sup/build/native-menu-offline-20260930-59qpxF/fixed
```

Log names in this order: permissions, native-port, binding, core,
menu-permission, menu-fixed, menu-recipe, native-variable, native-permission-arm,
reader-permission, reader-fixed (all `.log`). The JIT workloads require approved
host execution on this machine; earlier sandbox SIGILL is not a pass or a skip.
The permission ARM wrapper also converts a child JIT failure into a test failure.

## Limits and next gates

Host permission tests substitute the native registry and exclusion providers.
Native permission probes execute real attach, A2P, property storage, key dispatch
and cursor P2A with bounded framework substitutions. Native reader tests execute
real header, terminal and selector, but substitute intermediate component records
and allocator/owner services. Passing counts do not establish complete native
page construction, layout, focus navigation, actual exclusion or event drain.

The selector publishes a partial root if count/root survive an error; an isolated
mutation proves this. Reader initialization/cleanup occurs before the record seam,
so the missing outer-entry gate is a real installation blocker. Do not ship the
bridge alone, force-clear MainB2 cache, or overwrite existing OG hooks.
Permission type=0 does not drain an already-held repeat. Policy must recheck all
saved-value events; the port intentionally strips UI readiness. ON is unavailable
until the separate codec/writer/header/playback/storage/REC integration is proven.

Follow `fpSup/SUP_BUILD_RULES.md` for the future installable artifact: shared
loader, retained resident allocation, original parser trampoline, entry return,
D-before-I publication and journaled hooks. No card, camera, commit, push or
release actions were performed. AutoRun does not need an update for this offline
increment. Notify the user and obtain authorization before a camera trial.
