SIGMA fp AF HIGH-RATE OFFLINE TEST BUNDLE

NOT AF BETA. NOT HARDWARE VALIDATED. NOT DEPLOYMENT READY.
NO CAMERA INSTALLER AND NO USB TRANSPORT ARE INCLUDED.

The addresses below are explicit lab-model candidate inputs, not RAM leases.
Do not write them to a camera from this bundle.

capacity: 256
nonce: 0x20260916
maximum packet size: 1024

candidate layout:
  recorder: 0xD0000000..0xD00002D4 (724 bytes)
  sender: 0xD0001000..0xD00017E8 (2024 bytes)
  state: 0xD0002000..0xD0002040 (64 bytes)
  records: 0xD0002080..0xD000A080 (32768 bytes)
  dma_frame: 0xD000B000..0xD0013080 (32896 bytes)
  request: 0xD0014000..0xD0014020 (32 bytes)
  result: 0xD0014020..0xD0014040 (32 bytes)
  ops: 0xD0014040..0xD0014058 (24 bytes)
  veneer: 0xC0800000..0xC0800008 (8 bytes)

initial-capture.bin is an offline state+records concatenation, not an upload image.
manifest.json records safety flags plus recorded source and artifact hashes.
SHA256SUMS covers every emitted file except SHA256SUMS itself.
SHA256SUMS is written last and is the bundle-complete marker.
