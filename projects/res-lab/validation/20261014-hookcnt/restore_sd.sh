#!/bin/zsh
# Restore v21 (with this card's CFG) onto the SD mounted on the Mac, verify, eject.
set -e
V=${1:?volume path}
SRC=${0:A:h}/before-32RESCUS.BIN
[ "$(shasum -a 256 $SRC | cut -d' ' -f1)" = 797afea63e9edaecd31f392b1cf6ac30979cd9fddd5585a40490944708973928 ]
DST="$V/fpSup/32RESCUS.BIN"
[ -f "$DST" ]
cp "$DST" ${0:A:h}/bootfail-32RESCUS.BIN
cp "$SRC" "$DST"; sync
[ "$(shasum -a 256 "$DST" | cut -d' ' -f1)" = 797afea63e9edaecd31f392b1cf6ac30979cd9fddd5585a40490944708973928 ]
echo restored; diskutil eject "$V"
