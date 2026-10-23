#!/usr/bin/env python3
"""Recompute stats.npz offline for every resweep capture that still has its raw frame (status words are kept)."""
import pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import resweep
n = 0
for fj in pathlib.Path(sys.argv[1]).rglob('frame.json'):
    d = fj.parent
    if (d / 'frame.raw').exists():
        resweep.stats(d, live=False); n += 1
print('restat', n)
