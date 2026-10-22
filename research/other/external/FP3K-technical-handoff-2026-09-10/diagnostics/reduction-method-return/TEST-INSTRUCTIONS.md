# Reduction-method test — current everyday patch, no new AutoRun

Purpose: compare the 3K resampler against the stock UHD DC Crop RAW route,
which the offline firmware trace shows records before the RAW zoom block.
This is a noise/contribution test, not another field-of-view test. It can
separate single-sample selection from averaging under controlled conditions;
exact filter taps may still require a sharp-target or synthetic-input experiment.

Use the currently installed FP3K 0.3.5 full-height package. Do not install an
older diagnostic, wait for sampling text, remove the SD, or change to STILL.
Keep the SSD attached throughout. Use adequately charged power.

## Setup

- Point at a plain, evenly lit wall or white paper in steady daylight. Avoid
  screens and flickering lamps. Defocus strongly so there is no visible texture.
- Rest the camera on something stable. The wall should fill even the wider 3K
  view. This does not require subpixel registration, but movement, changing light
  or patterned subjects would contaminate the temporal noise measurement.
- CINE, manual exposure, CinemaDNG, 12-bit, true 24 fps, SSD. Set ISO 3200.
- Start with UHD and DC Crop ON. Set shutter to 1/50 second (172.8 degrees at
  24 fps). Adjust aperture for a comfortable midtone, well clear of clipping.
  Keep aperture, ISO, lens and lighting fixed for all four takes.
- Use REC and stop each recording yourself after approximately five seconds.
  Let the camera settle before each take. If a take stops itself, keep its files
  and report which take it was; do not erase it or retry repeatedly.

## Four takes, in this order

| Take | Resolution | DC Crop | Shutter |
| --- | --- | --- | --- |
| 1 | UHD | ON | 1/50 s / 172.8 degrees |
| 2 | UHD | ON | 1/100 s / 86.4 degrees |
| 3 | 3K | OFF | 1/50 s / 172.8 degrees |
| 4 | 3K | OFF | 1/100 s / 86.4 degrees |

After take 2, while UHD is still selected and recording has stopped, switch DC
Crop OFF, restore 1/50 second, then select 3K. Check the 3K HUD label for takes
3 and 4. The different crop framing is expected; do not move closer to compensate.
Changing shutter for take 4 should retain 3K; if it does not, note the behavior.

After take 4 select UHD, wait until the camera's media-access lamp is no longer
blinking, power off, and reconnect the media to the computer. Tell me whether all
four recordings completed normally. No still photos are needed for this test.

The computer return folders already exist here, including SD/FP3KM2,
SSD/FP3KM2 and clips. Leave the camera's recording directory names intact; the
files can be collected directly from the media.
