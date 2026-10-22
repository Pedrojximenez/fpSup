# r3j2 camera candidate — original preferences preserved

Same code and UI as [r3j2](../20261009-allsups-r3j2/README.md), with the pre-trial camera's full 128-byte FSDS table copied unchanged: disabled IDs FLIP and SHEL, count=2, unused slots zero. All final loader/UI/AutoRun bytes were read back from the camera and exactly match this directory.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| fpSup/LOADER.BIN | 27,428 | eede52236c08cf03dee596395434ee8847709facca2e3c49e70490f206c03828 |
| fpSup/UI/ALLSUPS.BIN | 289,895 | f7a640c92614906a32918d35c610fb0bd72152f20bc738d2a2e5b022ffce6ab0 |
| AutoRun.txt | 32,768 | 0c5107fff1262ad8ca3bb675329b71c80926c8b35cdd40931b387639b45edbf0 |

USB-Shell was temporarily enabled to retain connectivity over two trial reboots, then restored to its original next-boot disabled preference. It remains loaded in the final current boot and shows Unload on restart; no reboot was performed after restoring SHEL. Flip is currently unloaded and remains disabled. The original six product files were preserved; temporary 60BTN.BIN was removed.

This directory contains no product Sups and is not a full replacement for another card. Its disabled IDs belong to this camera's saved preference. Evidence: [trial results](../20261009-allsups-r3j-live1/RESULTS.md), [final full readbacks](../20261009-allsups-r3j-live1/final-readback.json).
