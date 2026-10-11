# Launch-stage idle run: passed

Returned SSD output contains one clean, unnumbered set. Loaded payload matches the verified 1020-byte code; allocation readback matches the capture header. All 120 samples completed, with sensor mode 8, RAW profile 5, recording flags zero, no transition flags, and no differences from the stock profile parameters.

PRE.BIN = 0xC03D99A0 (original echo handler), ARMED.BIN = 0xC072DE64 (diagnostic entry), RETURN.BIN = 0xC03D99A0 (original handler restored). Camera timestamps: ARMED 04:48:08, STATE and RETURN 04:48:41 on camera date 2050-03-16. These are camera filesystem times, not calibrated elapsed-time measurements.

User reports the LCD slept; turning a dial woke it with no green overlay. File evidence proves this run completed despite the missing overlay. The timing of the dial movement relative to sampling is unknown. This does not validate recording compatibility or establish the cause of the preceding incomplete return, which the user may have powered off early.

Next: one short UHD24 recording using the original payload/script, without the extra stage readbacks. Fresh media output folders and separate workspace return directories required.
