# USB automation setup

Mac IORegistry detects Sigma fp 1003:c432 at 5 Gbit/s. Read-only libusb descriptor check outside sandbox succeeds: stock interface class 06/01/01, bulk OUT 01 and IN 82, interrupt IN 83. Sandbox descriptor access alone failed to open device.

Stock PTP GetDeviceInfo probe outside sandbox was denied when claiming interface 0 (LIBUSB_ERROR_ACCESS). No PTP request was sent, no driver detached, no settings or firmware changed. The exact macOS access restriction was not established.

Built upstream fpshd and lsdesc with installed libusb. Prepared classic single-file upstream shell AutoRun with FP_USB_READY banner, no padding, no added imaging payload. Static checks validate firmware MAIN hash, zero cave, original bootstrap instruction, complete allowed write set, code bytes and script size. This does not constitute full worker emulation or hardware validation. Package remains on Mac, not deployed.

Next user step: power camera off, disconnect USB, mount SD card in Mac. Agent can back up existing AutoRun, install and verify new file after identifying the volume. First shell boot must be disconnected from USB until loading finishes; then reconnect for descriptor and ping checks. No SSD recording or FPD003 sampler while establishing this shell.

## First USB-shell connection: passed

Vendor interface ff/ff/ff enumerates at SuperSpeed. Ping succeeds. All 1608 worker code bytes match the build, all ten endpoint/display patch words match, original gyro callback instruction is restored, and allocation descriptor reports 1 MiB. Worker status reads and bounded RAM reads succeed. Raw pipeline state is mode 8/profile 5, selected route [1,5,8,...], with no differences from stock parameters. This matches previous idle results.

Host descriptor for unused EP83 remains bulk/64 bytes/interval11 despite its template words matching the intended 1024-byte/interval0 patch. Cause is unresolved; do not use this endpoint for streaming. EP01/82 command transport works. No image recording, sensor change, additional injected payload, or camera file transfer was performed during this validation.

Upstream host/fpsh incorrectly reports OKX replies as failures; tools/check_usb_shell.py decodes these correctly, restricts reads to 128-byte chunks and retries only reads. tools/read_usb_raw_state.py obtains bounded snapshots, not atomic capture. Local daemon runs in exec session 22493 at /tmp/fpware-fpshd.sock. The camera must remain powered on/connected to use it.
