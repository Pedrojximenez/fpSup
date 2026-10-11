#!/usr/bin/env python3
"""Offline structural validation of fp 5.02 completed Near / area-0 histories.

No USB imports or camera actions. This checks a narrow, verified strategy, not
all AF modes. Stable old history can pass: freshness and optical alignment need
separate trial evidence. Never rewrite a probe's raw JSON to mark it valid.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


BLOCKS = {
    "near_object": (0xC3206BE4, 38),
    "sweep_descriptor": (0xC320680C, 24),
    "af_globals": (0xC32914E0, 24),
    "mposm": (0xC3291958, None),
    "aggregate_contrast": (0xC32938A8, None),
    "area0_h_history": (0xC329B128, None),
    "area0_l_history": (0xC32CCE08, None),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def signed(word):
    return word - 0x100000000 if word & 0x80000000 else word


def native_round(value):
    """C067E2AC -> C067F804: nearest integer, ties away from zero."""
    return math.floor(value + 0.5) if value >= 0 else -math.floor(-value + 0.5)


def peak_candidate(samples, native_peak, selected_peak):
    """Reconstruct the interior branch, not the whole native decision tree.

    Firmware may choose another statistic or interpolation branch. A numerical
    match is a cross-check, not evidence that those uncaptured flags were set.
    """
    result = {
        "native_formula_candidate_position": None,
        "near_peak_position": native_peak,
        "near_selected_position": selected_peak,
        "matches_near_peak": None,
        "matches_near_selected": None,
        "scope": "interior H-maximum branch candidate; not full firmware replay",
    }
    xs = [row["position"] for row in samples]
    ys = [row["h"] for row in samples]
    if len(xs) < 3:
        result["reason"] = "fewer than three samples"
        return result
    steps = [b - a for a, b in zip(xs, xs[1:])]
    if not (all(v > 0 for v in steps) or all(v < 0 for v in steps)):
        result["reason"] = "positions are not strictly monotonic"
        return result
    if ys.count(max(ys)) != 1:
        result["reason"] = "tied H maximum"
        return result
    k = ys.index(max(ys))
    result["h_argmax"] = k
    if k in (0, len(xs) - 1):
        result["reason"] = "endpoint peak: native endpoint branch not implemented"
        return result
    if max(ys) > 2**24:
        result["reason"] = "large statistics: native numeric conversion not modeled"
        return result
    left = abs(xs[k] - xs[k - 1])
    right = abs(xs[k + 1] - xs[k])
    rise = (ys[k] - ys[k - 1]) * right / left
    fall = (ys[k] - ys[k + 1]) * left / right
    difference = rise - fall
    denominator = max(1.0, rise + fall)
    spacing = right if difference >= 0 else left
    offset = 0.5 * spacing * difference / denominator
    correction = native_round(offset)
    correction = min(correction, right // 2) if correction >= 0 else max(correction, -(left // 2))
    direction = 1 if steps[0] > 0 else -1
    candidate = xs[k] + direction * correction
    # Ordinary unequal-spacing quadratic fit, reported separately. It is NOT
    # the native weighted-difference formula above.
    a, b = xs[k - 1] - xs[k], xs[k + 1] - xs[k]
    ya, yb = ys[k - 1] - ys[k], ys[k + 1] - ys[k]
    curvature = (ya / a - yb / b) / (a - b)
    slope = ya / a - curvature * a
    result.update(
        native_formula_candidate_position=candidate,
        native_formula_float_offset=offset,
        native_formula_rounded_offset=correction,
        ordinary_quadratic_vertex=xs[k] - slope / (2 * curvature),
        matches_near_peak=candidate == native_peak,
        matches_near_selected=candidate == selected_peak,
        reason="interior candidate calculated",
    )
    return result


def analyze_history(data):
    require(isinstance(data, dict), "history must be an object")
    require(data.get("mode") == "read-only-native-history", "unsupported probe mode")
    passes = data.get("passes")
    require(isinstance(passes, list) and len(passes) == 2, "exactly two passes required")
    for snapshot in passes:
        require(isinstance(snapshot, dict) and set(snapshot) == set(BLOCKS), "unexpected blocks")
        lengths = []
        for name, (address, count) in BLOCKS.items():
            block = snapshot.get(name)
            require(isinstance(block, dict), name + ": missing block")
            try:
                actual_address = int(block.get("address"), 0)
            except (TypeError, ValueError):
                raise ValueError(name + ": invalid address") from None
            require(actual_address == address, name + ": wrong address")
            words = block.get("words")
            require(isinstance(words, list), name + ": missing words")
            require(all(type(w) is int and 0 <= w <= 0xFFFFFFFF for w in words), name + ": invalid u32")
            if count is None:
                require(1 <= len(words) <= 128, name + ": prefix length outside 1..128")
                lengths.append(len(words))
            else:
                require(len(words) == count, name + ": incorrect block length")
        require(len(set(lengths)) == 1, "history arrays have different lengths")
    full_equal = passes[0] == passes[1]
    if "two_passes_equal" in data:
        require(type(data["two_passes_equal"]) is bool and data["two_passes_equal"] == full_equal,
                "two_passes_equal flag disagrees with raw data")
    differences = []
    for name, (address, _) in BLOCKS.items():
        first, second = passes[0][name]["words"], passes[1][name]["words"]
        require(len(first) == len(second), name + ": pass lengths differ")
        for i, (a, b) in enumerate(zip(first, second)):
            if a == b:
                continue
            # C023EC28 refreshes C32914FC from current area-0 L minus an
            # adjustment, independently of Near completion. No other
            # difference is whitelisted (blk_c02.c:44448).
            require(name == "af_globals" and i * 4 == 0x1C,
                    f"unstable history/metadata at {address + i * 4:#010x}")
            differences.append({"address": f"0x{address+i*4:08X}", "before": a, "after": b,
                                "reason": "live L reference, not a stored history element"})
    snapshot = passes[0]
    obj = snapshot["near_object"]["words"]
    desc = snapshot["sweep_descriptor"]["words"]
    glob = snapshot["af_globals"]["words"]
    require(obj[0x38 // 4] == 0xC091F134, "not a supported Near vtable")
    require(obj[0x28 // 4] & 0xFF == 1, "Near completion byte is not 1")
    require(obj[0x18 // 4] in (4, 6), "unsupported completed Near state")
    require(obj[0x10 // 4] == 0, "nonzero Near interpolation index offset is not modeled")
    n, d = signed(obj[0x3C // 4]), signed(obj[0x08 // 4])
    require(0 <= d <= n < 1000, "unsupported raw count/delay")
    count = n - d + 1
    require(desc[0x08 // 4] == count, "descriptor count disagrees with completed position prefix")
    require(desc[0x50 // 4] == d, "descriptor delay disagrees with Near")
    for offset, name in ((0x40, "aggregate_contrast"), (0x44, "area0_h_history"),
                         (0x48, "area0_l_history"), (0x4C, "mposm")):
        require(desc[offset // 4] == BLOCKS[name][0], "unexpected descriptor " + name + " pointer")
    require(glob[0x34 // 4] == 0 and glob[0x54 // 4] == 0,
            "selected/live area is not verified area 0")
    available = len(snapshot["mposm"]["words"])
    require(count <= available, "captured prefix is shorter than valid history")
    samples = [dict(k=k, position=signed(snapshot["mposm"]["words"][k]),
                    h=snapshot["area0_h_history"]["words"][k],
                    l=snapshot["area0_l_history"]["words"][k],
                    aggregate=snapshot["aggregate_contrast"]["words"][k]) for k in range(count)]
    return {
        "schema": "sigma-fp-near-history-analysis/v1",
        "status": "completed-near-area0-structural-candidate",
        "full_dump_stable": full_equal,
        "history_stable": True,
        "permitted_live_differences": differences,
        "freshness_confirmed": None,
        "usable_for_dfd": None,
        "limitations": ["May be stale: verify a new sweep in trial telemetry separately.",
                        "No independent optical/motor timing ground truth.",
                        "H/L are CDAF frequency bands, not phase-detection halves.",
                        "Exposure/gain is not attached per native history sample."],
        "metadata": {"state": obj[0x18 // 4], "raw_n": n, "delay_d": d,
                     "valid_count": count, "captured_prefix_count": available,
                     "excluded_tail_count": available - count,
                     "descriptor_direction_raw": desc[0x2C // 4],
                     "global_command_position": signed(glob[0])},
        "samples": samples,
        "peak": peak_candidate(samples, signed(obj[0x64 // 4]), signed(obj[0x7C // 4])),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("history", type=Path)
    parser.add_argument("--output", type=Path, help="New JSON only; otherwise print to stdout")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error("output already exists; never overwrite raw evidence")
    try:
        raw = args.history.read_bytes()
        result = analyze_history(json.loads(raw))
    except (ValueError, OSError) as exc:
        parser.exit(2, f"history rejected: {exc}\n")
    result["source"] = str(args.history.resolve())
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
    if args.output:
        with args.output.open("x") as output:
            output.write(encoded)
        print(args.output)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
