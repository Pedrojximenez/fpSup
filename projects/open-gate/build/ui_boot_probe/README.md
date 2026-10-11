# GUI resource-parser boot timing probe

This is an observation-only card for Sigma fp firmware Ver.5.02. It does not
install OG3K and does not change any capture setting. Its only question is
whether AutoRun can arm a hook before the one-time GUI resource parse.

## Card files

Copy `AutoRun.txt` and `VSHL.BIN` together. They are a matched pair; verify both
hashes against `MANIFEST.txt`. Back up and remove any existing card boot files
first instead of overwriting them in place.

## Run

1. Fully power off, remove the battery, and use a card reader to install the two
   files. This must be a cold boot, not a restart.
2. Boot with USB unplugged and wait for `UIBOOT!`.
3. Do not open Quick Set, change resolution, or switch screens before reading.
4. Attach USB and run from the SIGMAfp_re root:

   `python3 research/ui/tools/appendobs_ctl.py read`

The reader first verifies the complete 76-byte payload and
the hook word. Only then is the cursor interpreted:

- cursor above `0xC0733100` on a 12-byte boundary: the observer saw boot-time
  resolution-array construction, so an append hook is viable;
- cursor exactly `0xC0733100` with a valid payload and hook: AutoRun was too
  late for that construction pass;
- any payload, hook, or cursor mismatch: loading failed, so it is not a timing
  result.

The probe owns `0xC0733000..0xC0734000` and is mutually exclusive with the
other UI observer tools that use the same cave. Remove both files, restore the
backed-up card set, and cold boot to return to stock.
