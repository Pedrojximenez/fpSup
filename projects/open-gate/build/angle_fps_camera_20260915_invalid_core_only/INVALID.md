# Invalid angle-FPS live-view run — 2026-09-15

Do not use these screenshots as FHD/OG3K evidence.

The camera had received the 707-word core through the live first-install loader,
but the complete native-UI candidate had not been installed from the card on a
battery-out cold boot. `menu SetMovRecSize` returned `4`; the user correctly
observed that OG3K was not actually shown/confirmed on the camera. Treat every
purported enum-4 screenshot in this directory as unconfirmed FHD-like output.

One approximately one-second FHD clip, `A001_098`, was created before the user
requested idle-live-view-only testing. No OG3K recording was made. The user's
unrelated freeze report remains excluded from this run.

After this invalid run, the complete debug candidate was written to the card
and read back byte-for-byte:

- `VSHL.BIN`: `d573bfc897569a5fd4f8d647e4f2b7d29e19208f65553c72d687c2a8874ac2ec`
- `AutoRun.txt`: `3a2a58c9b7f20db8a2f47d0a62774fd1aabb8c396e734fe4780fac0e6b5f7c53`

A new battery-out cold boot with USB unplugged is required before repeating
the live-view comparison.
