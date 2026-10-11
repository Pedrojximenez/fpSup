#!/usr/bin/env python3
"""Offline exploratory H/L direction diagnostics from completed AF histories.

No camera/USB imports. Native H-derived peaks are reference labels, NOT optical
truth. Pair agreement is an internal consistency diagnostic, not accuracy.
Every source history is structurally revalidated; original files are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

from af_fusion_history_analyze import analyze_history, require


def sign(value):
    return (value > 0) - (value < 0)


def level_crossings(points, level):
    """Piecewise-linear illustrative intersections; never extrapolate.

    Flat segments exactly on the level are returned as intervals, not invented
    unique positions. These are interpolations, not additional measurements.
    """
    found, intervals = [], []
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if y0 is None or y1 is None:
            continue
        if y0 == y1:
            if y0 == level:
                intervals.append(sorted([x0, x1]))
            continue
        if min(y0, y1) <= level <= max(y0, y1):
            x = x0 + (level - y0) * (x1 - x0) / (y1 - y0)
            if not any(math.isclose(x, old, rel_tol=0, abs_tol=1e-8) for old in found):
                found.append(x)
    return {"positions": found, "flat_intervals": intervals}


def analyze_curve(history, ratio_level=0.19):
    require(math.isfinite(ratio_level) and ratio_level > 0, "ratio level must be finite and positive")
    peak = history["peak"]["near_peak_position"]
    require(history["peak"]["matches_near_peak"] is True,
            "requires a matched native interior H-peak candidate")
    rows = [dict(row, position_minus_native_peak=row["position"] - peak,
                 h_over_l=row["h"] / row["l"] if row["l"] else None)
            for row in history["samples"]]
    require(len(rows) >= 3, "at least three samples required")
    steps = [b["position"] - a["position"] for a, b in zip(rows, rows[1:])]
    require(all(x > 0 for x in steps) or all(x < 0 for x in steps),
            "strictly monotonic positions required")
    lower = [r for r in rows if r["position"] < peak]
    higher = [r for r in rows if r["position"] > peak]
    require(lower and higher, "native reference peak must be bracketed")
    metrics, pairs = {}, []
    for metric in ("h", "l", "h_over_l"):
        usable = [r for r in rows if r[metric] is not None]
        maximum = max((r[metric] for r in usable), default=None)
        maxima = [r for r in usable if r[metric] == maximum]
        low_values = [r[metric] for r in lower if r[metric] is not None]
        high_values = [r[metric] for r in higher if r[metric] is not None]
        overlap = None
        if low_values and high_values:
            lo, hi = max(min(low_values), min(high_values)), min(max(low_values), max(high_values))
            if lo <= hi:
                overlap = [lo, hi]
        metrics[metric] = {
            "sample_argmax_indices": [r["k"] for r in maxima],
            "sample_argmax_positions": [r["position"] for r in maxima],
            "argmax_has_endpoint": any(r is rows[0] or r is rows[-1] for r in maxima),
            "opposite_side_sample_range_overlap": overlap,
            "same_side_pair_count": 0,
            "same_side_agree_with_native_H_reference": 0,
            "same_side_abstain_count": 0,
            "same_side_disagree_count": 0,
        }
    for first, second in zip(rows, rows[1:]):
        x0, x1 = first["position"], second["position"]
        lo, hi = sorted([x0, x1])
        crossing = lo <= peak <= hi
        target_direction = None if crossing else sign(peak - x1)
        item = {"from_k": first["k"], "to_k": second["k"], "delta_position": x1 - x0,
                "crosses_or_touches_native_peak": crossing,
                "target_direction_from_second_point": target_direction, "metrics": {}}
        for metric, stats in metrics.items():
            v0, v1 = first[metric], second[metric]
            gradient_direction = None if v0 is None or v1 is None else sign((v1 - v0) / (x1 - x0))
            item["metrics"][metric] = {"delta": None if v0 is None or v1 is None else v1 - v0,
                                       "gradient_direction": gradient_direction}
            if not crossing:
                stats["same_side_pair_count"] += 1
                if gradient_direction in (None, 0):
                    stats["same_side_abstain_count"] += 1
                elif gradient_direction == target_direction:
                    stats["same_side_agree_with_native_H_reference"] += 1
                else:
                    stats["same_side_disagree_count"] += 1
        pairs.append(item)
    crossings = level_crossings([(r["position"], r["h_over_l"]) for r in rows], ratio_level)
    return {"native_H_reference_peak": peak, "samples": rows, "metrics": metrics,
            "pairs": pairs, "crossing_pairs_excluded_from_agreement": sum(
                p["crosses_or_touches_native_peak"] for p in pairs),
            "illustrative_ratio_level": ratio_level,
            "ratio_level_piecewise_linear_crossings": crossings}


def load_trial(path, ratio_level):
    raw = path.read_bytes()
    history = analyze_history(json.loads(raw))
    manifest_path = path.parent / "manifest.json"
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    require(manifest.get("handler_transport") == "cpu-copy-to-worker-dma-buffer/v1",
            "exclude unverified/direct-code-cave DMA transport")
    require(manifest.get("mode") == "live-original-af-trial", "original AF trial evidence required")
    require(manifest.get("release_transport_completed") is True and
            manifest.get("release_still_required") is False, "release evidence incomplete")
    result = analyze_curve(history, ratio_level)
    result.update(source=str(path.resolve()), source_sha256=hashlib.sha256(raw).hexdigest(),
                  manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
                  name=path.parent.name, source_full_dump_stable=history["full_dump_stable"],
                  transport_counters={k: manifest.get(k) for k in (
                      "records_written", "invalid_replies", "duplicate_records", "stale_session_replies",
                      "out_of_order_records", "camera_sequence_gaps")})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("histories", type=Path, nargs="+")
    parser.add_argument("--ratio-level", type=float, default=0.19,
                        help="Illustrative piecewise-linear level, not a learned classification threshold")
    parser.add_argument("--output", type=Path, help="New JSON file, or omit for stdout")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("output exists; never overwrite evidence")
    try:
        require(len({p.resolve().parent for p in args.histories}) == len(args.histories),
                "do not count a reread from the same trial twice")
        trials = [load_trial(path, args.ratio_level) for path in args.histories]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f"direction replay rejected: {exc}\n")
    report = {
        "schema": "sigma-fp-direction-diagnostic/v1", "mode": "offline-exploratory",
        "camera_touched": False, "optical_direction_validated": False, "usable_for_dfd": None,
        "limitations": [
            "All labels use native H-derived peaks, not independent optical truth.",
            "Pair agreement is in-sample internal consistency, not held-out prediction accuracy.",
            "Lower/higher position is not independently calibrated near/far distance.",
            "A range overlap is not an observed equal-value pair; crossings are explicitly interpolated.",
            "No per-history-sample gain/filter normalization is justified by this dataset.",
            "The displayed ratio level is illustrative, not a learned controller threshold.",
        ],
        "trials": trials,
        "totals": {metric: {key: sum(t["metrics"][metric][key] for t in trials)
                              for key in ("same_side_pair_count", "same_side_agree_with_native_H_reference",
                                          "same_side_abstain_count", "same_side_disagree_count")}
                   for metric in ("h", "l", "h_over_l")},
        "crossing_pairs_excluded_from_agreement": sum(t["crossing_pairs_excluded_from_agreement"] for t in trials),
    }
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as output:
            output.write(encoded)
        print(args.output)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
