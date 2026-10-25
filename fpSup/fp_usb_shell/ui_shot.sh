#!/bin/sh
# ui_shot.sh N TAG [OUTDIR]: screenshot, then fetch \DCIM\100SIGMA\SS__N.JPG by number.
# For when ui_drive.py shot says "no new screenshot appeared": the `dir` reply is
# capped at 16 KB (~300 files), so new shots exist but are not listed (2026-10-25).
# N = the last screenshot's number + 1.
cd "$(dirname "$0")"
OUT=${3:-/tmp/fp_ui}; mkdir -p "$OUT"
python3 -B -c "
import sys; sys.path.insert(0,'.'); from putfile import sh
sh('key CAPTUREON', retries=0); sh('key CAPTUREOFF', retries=0)"
sleep 3
sz=$(python3 -B getfile.py "\\DCIM\\100SIGMA\\SS__$1.JPG" /dev/null --size 300000 2>&1 | grep -o 'file length is [0-9]*' | grep -o '[0-9]*$')
[ -n "$sz" ] || { echo "SS__$1.JPG not found"; exit 1; }
python3 -B getfile.py "\\DCIM\\100SIGMA\\SS__$1.JPG" "$OUT/$2.jpg" --size "$sz" >/dev/null 2>&1 && echo "$OUT/$2.jpg"
