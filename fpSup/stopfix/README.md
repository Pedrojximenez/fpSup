# Standalone stop-queue release patch

`05STOPFX.BIN` is an independent Loader v3 module for SIGMA fp Ver.5.02. It
redirects `C0377118` to native reference-counted release at `C03776A0`. It does
not require the lossless module and does not implement frame-count optimization.

The reviewed file is 316 bytes, SHA-256
`f9f26a092c5676ead5771ba8be4aac9c3734e9ed0cd144002a73b3f6b657c9d9`.
`stopfix_fixture.py` reproduces those exact bytes with the shared patch builder.

Run this module's offline tests from this directory:

```sh
python3 -B -X faulthandler -m unittest test_stop_release
```

Cross-module compatibility tests live separately in `../integration_tests/`.
LOSS builds and tests do not import or build this module.

Offline verification has not established hardware timing or all concurrent
release cases; the stock registry-busy early return remains a limitation.
The patch cannot recover discarded images or allocations already lost before
installation. See the original review in
`../../projects/lossless-sup/validation/20261011-community-stopfix/`.

The historical `20261012-bulk-stop-integration` candidate embedded this patch
in LOSS and conflicts with the standalone BIN. Later independent LOSS builds
do not own the stop-release site.
