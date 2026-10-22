# Preview3 return review

Review completed before everyday loader installation. The results support
installing the same resident without the temporary sampler.

- Exact expected resident and sampler hashes; boot status 16, no patch or UI
  error codes in 56 captured samples.
- The display-fit hook's applied bit is set. Stable 3K preview states show
  2000×1334 source/native crop and 1620×1080 primary output.
- Stock UHD geometry returns after selection: 2000×1125 preview crop,
  1620×911 standby output and 1920×1080 recording output.
- QS seen/extended bitmaps are 5/5.
- A001_021: 135 frames, 5.625 seconds, 3000×2000 crop, 12-bit, metadata 24 fps.
- A001_022: 144 frames, 6 seconds, 3840×2160 crop, 12-bit, metadata 24 fps.
- Every frame passed numbering, metadata and strip-bound checks. Every RAW
  payload is distinct within its clip. Both audio files are readable.
- Nine sampled 3K images and three UHD images show no obvious corruption.

All 283 recording files (3,071,995,478 bytes) and eight diagnostic files were
copied and hash-verified. Originals remain on the media.

The trace starts too late to include the active 3K recording state; the 3K
recording is checked directly from its files. Latched layout bits show that the
hook ran, not continuous rendering. Transitions briefly contain stale source
geometry. These checks do not certify sensor cadence, all-photosite filtering
or extended reliability. The user separately confirmed successful full-height
LCD preview.
