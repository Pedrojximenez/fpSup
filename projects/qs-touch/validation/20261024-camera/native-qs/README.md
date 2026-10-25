# Native QS trial — 2026-10-24

v0.2.0test ZQS.BIN was fully read back, QSTOUCH.BIN removed, then one standby
reboot completed. LOAD.LOG confirms ZQS has three claims, Res-Custom retained
its 0x75 claims and Tap to Zoom is disabled for the authorized touch trial.
Opening through original QSON activated QSN_Active and displayed the new text
faces in original QS_CINE. This is native-entry evidence, not physical-touch
or setting-commit proof. Last captured raw packet count was zero.

A mismatch remains: RES showed UHD while a later native menu getter returned
2 (FHD). v0.2.1 removes duplicate two-way holders and keeps original dial/
value owners byte-for-byte. The cause and fix still need camera validation.

A standby query timed out. The host daemon later had PID 67911 instead of
this trial's PID 64181, with no restart action from this trial. This does not
establish a camera freeze or its cause. Further camera commands stopped and
physical state was requested.

The first candidate passed ten offline tests and three mutations. See the
individual artifact verification for the new candidate's status.
No additional backup or recording was performed. Tap to Zoom must be restored
when the physical touch trial ends. Full repeated power-switch/card acceptance
and the advanced prototype controls are not complete.
