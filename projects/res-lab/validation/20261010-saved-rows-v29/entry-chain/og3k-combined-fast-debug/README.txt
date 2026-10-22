fpGyroSup og3k+gyro-v1.11b -- SIGMA fp firmware Ver.5.02 only

Put AutoRun.txt and fpSup.BIN in the root of the SD card the camera boots
from, and record CinemaDNG.  Nothing else: no folder to make, no file to
convert, no step after the take.

Each take writes both of the files Gyroflow wants, inside the clip's own
folder, while it is being recorded:

    \CINEMA\A001_037\A001_037.gcsv    the IMU log
    \CINEMA\A001_037\A001_037.json    the lens profile

Load the frames and both files into Gyroflow and run its synchronisation as
usual.  There is nothing to convert, but the offset still has to be found:
CinemaDNG carries no timecode, and the log starts about half a second after
the first frame -- measured between 470 and 570 ms, and different every take --
so it is not a number you can fill in once and reuse.

The log is every sample the gyro produced -- 2499.466 Hz, nothing averaged and
nothing dropped -- with each accelerometer reading placed on the row of the
sample it followed.  The profile carries the lens's own distortion, read out
of the camera's calibration data for whatever is mounted, so it is the same
curve the camera puts in a DNG's WarpRectilinear opcode.

Portrait takes need nothing done to them.  In CINE the camera records every
frame landscape upright, so Gyroflow reads a portrait take exactly as it
reads a landscape one: load the frames and the two sidecars, sync, stabilise,
and turn the picture at the end of the edit.  Leave horizon lock off.
Photographs are untouched and still rotate by themselves.

CinemaDNG only.  A MOV take gets no sidecars: MOV records through a different
path this build does not hook.  Use fpGyroSup Base for MOV -- it writes a .GYR
beside any take -- or v1.1 of this line.

This is a DEVELOPMENT card, not the card a user downloads.

It carries the USB shell: the camera exposes a command channel over USB
while this card is booted.

It also carries FAST START, which writes a loader into the camera's settings
block (XC_CommonSaveData) on the first boot.  That write SURVIVES A BATTERY
PULL and survives deleting AutoRun.txt.  Removing the two files does NOT put the
camera back exactly as it was; the seeded block stays until it is cleared.

Fast start has been booted on a shell-only card.  It has NOT been booted on a
combined card like this one.

