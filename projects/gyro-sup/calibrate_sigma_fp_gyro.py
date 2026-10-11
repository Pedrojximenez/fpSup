#!/usr/bin/env python3
"""Estimate SIGMA fp gyro axis mapping and offset from a DNG sequence."""

from __future__ import annotations

import argparse
import csv
import glob
from pathlib import Path

import cv2
import numpy as np
import rawpy


def read_gray(path: str, step: int = 4) -> np.ndarray:
    with rawpy.imread(path) as raw:
        image = raw.raw_image_visible[::step, ::step].astype(np.float32)
    lo, hi = np.percentile(image, (1, 99.5))
    image = np.clip((image - lo) * (255.0 / max(hi - lo, 1)), 0, 255)
    return image.astype(np.uint8)


def visual_motion(paths: list[str]) -> np.ndarray:
    previous = read_gray(paths[0])
    height, width = previous.shape
    center = np.array([width / 2, height / 2])
    rows = []
    for index, path in enumerate(paths[1:], 1):
        current = read_gray(path)
        points = cv2.goodFeaturesToTrack(previous, 500, 0.01, 6, blockSize=5)
        matrix = None
        if points is not None:
            moved, status, _ = cv2.calcOpticalFlowPyrLK(
                previous, current, points, None, winSize=(31, 31), maxLevel=4
            )
            good0, good1 = points[status.ravel() == 1], moved[status.ravel() == 1]
            if len(good0) >= 12:
                matrix, _ = cv2.estimateAffinePartial2D(
                    good0, good1, method=cv2.RANSAC, ransacReprojThreshold=2.0
                )
        if matrix is None:
            rows.append((np.nan, np.nan, np.nan))
        else:
            angle = np.arctan2(matrix[1, 0], matrix[0, 0])
            mapped_center = matrix[:, :2] @ center + matrix[:, 2]
            dx, dy = mapped_center - center
            rows.append((dx, dy, angle))
        previous = current
        if index % 50 == 0:
            print(f"frames {index}/{len(paths)-1}", flush=True)
    data = np.asarray(rows)
    for column in range(3):
        bad = ~np.isfinite(data[:, column])
        data[bad, column] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), data[~bad, column])
    return data


def read_gcsv(path: Path) -> tuple[np.ndarray, np.ndarray]:
    times, gyro = [], []
    with path.open(newline="") as handle:
        rows = csv.reader(handle)
        for row in rows:
            if len(row) == 4 and row[0].lstrip("-").isdigit():
                times.append(float(row[0]) * 1e-6)
                gyro.append(tuple(map(float, row[1:])))
    return np.asarray(times), np.asarray(gyro)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dng_glob")
    parser.add_argument("gcsv", type=Path)
    parser.add_argument("--fps", type=float, default=30000 / 1001)
    parser.add_argument("--output", type=Path, default=Path("visual_motion.csv"))
    args = parser.parse_args()
    paths = sorted(glob.glob(args.dng_glob))
    if len(paths) < 3:
        raise SystemExit("not enough DNG frames")
    motion = visual_motion(paths)
    np.savetxt(args.output, motion, delimiter=",", header="dx,dy,roll_rad", comments="")
    times, gyro = read_gcsv(args.gcsv)
    frame_times = (np.arange(len(motion)) + 0.5) / args.fps
    names = ("image_dx(yaw)", "image_dy(pitch)", "image_roll")
    axes = "XYZ"
    print("\nBest gyro match per visual channel:")
    for visual_index, name in enumerate(names):
        visual = motion[:, visual_index]
        visual = visual - np.median(visual)
        best = None
        for axis in range(3):
            for offset in np.arange(-5.0, 1.001, 0.005):
                sampled = np.interp(frame_times + offset, times, gyro[:, axis], left=np.nan, right=np.nan)
                valid = np.isfinite(sampled)
                if valid.sum() < 100:
                    continue
                a, b = visual[valid], sampled[valid]
                corr = np.corrcoef(a, b)[0, 1]
                score = abs(corr)
                if best is None or score > best[0]:
                    scale = np.dot(a, b) / max(np.dot(b, b), 1e-12)
                    best = (score, corr, offset, axes[axis], scale)
        print(name, best)


if __name__ == "__main__":
    main()
