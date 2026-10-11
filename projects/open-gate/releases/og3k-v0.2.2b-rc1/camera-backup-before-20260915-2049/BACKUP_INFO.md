# Camera-card rollback backup

Captured from the connected SIGMA fp immediately before staging OG3K v0.2.2b-RC1.

The two files match the known `og2k_candidate` build exactly:

- `AutoRun.txt`: `39324f62354392522cf5d0620a1dc427d6e62d10739d63efbc54c695bc8179e1`
- `VSHL.BIN`: `08796efb53a3a5d52273f4c4901c214077c8185fcb6a71eabec497f05f3c1b70`

Restore both files together, then perform a complete battery-out cold boot with USB disconnected.

## RC1 staging result

The camera card was updated in the safe order `VSHL.BIN` first, `AutoRun.txt` last. Both files were then read back from the card and matched the local RC1 byte-for-byte:

- `RC1-readback-AutoRun.txt`: `8836b3703f5196e948739a49cd11877191ce8f540d8aaedf81a429713d95384c`
- `RC1-readback-VSHL.BIN`: `da1c94e05828c7fec423fed044856d54ba839532d38a5bd2e446942778062cd7`

The files have not yet executed. Activation requires a complete battery-out cold boot with USB disconnected.
