#!/usr/bin/env python3
"""Read native cached focus position/edges and distance conversions, fp 5.02.

No code injection, focus drive, wait, stop, menu setter or capture command.
Uses the initialized native-L lens path. Getter outputs are cached/table values,
not an independent optical measurement or a guarantee of motion completion.
"""
import argparse
import datetime as dt
import json
from pathlib import Path
import re
from types import SimpleNamespace

import af_fusion_collector as collector


READ_COMMANDS = {"getfpos", "getfedge", "cnvfpos", "cnvfdist"}


def read_lens(shell, name, value, transcript):
    if name not in READ_COMMANDS or (value is not None and type(value) is not int):
        raise ValueError("only audited integer-argument read commands are allowed")
    if value is not None and not -0x80000000 <= value <= 0x7FFFFFFF:
        raise ValueError("argument outside signed-32 input domain")
    if name == "getfpos" and value is not None:
        raise ValueError("getfpos takes no argument")
    if name == "getfedge" and value not in (0, 1):
        raise ValueError("getfedge selector must be 0 or 1")
    if name in ("cnvfpos", "cnvfdist") and value is None:
        raise ValueError("explicit conversion input required")
    command = "lens " + name + (" " + str(value) if value is not None else "")
    reply = collector._daemon_request(shell, "TMO 1000 SHL " + command)
    transcript.append({"command": command, "reply": reply.decode("ascii", errors="replace")})
    if not reply.startswith(b"OK "):
        raise RuntimeError("read command failed: " + repr(reply))
    body = reply[3:].decode("ascii").replace("\\n", "\n").strip()
    match = re.fullmatch(r"lens\s+" + name + r"\s+(-?\d+)", body)
    if not match:
        raise RuntimeError("unexpected read format: " + repr(body))
    result = int(match.group(1))
    bounds = (0, 0xFFFFFFFF) if name == "cnvfdist" else (-0x80000000, 0x7FFFFFFF)
    if not bounds[0] <= result <= bounds[1]:
        raise RuntimeError("native result outside declared integer domain")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default=collector.DEFAULT_SOCKET)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    if not args.output.parent.is_dir():
        parser.error("output parent directory must already exist")
    evidence = {"started_at": dt.datetime.now().astimezone().isoformat(),
                "mode": "native-cached-read-and-convert-only", "transcript": [],
                "position_step_for_conversion_only": 100, "lens_movement_requested": False}
    shell = SimpleNamespace(SOCK=args.socket)
    try:
        with collector._exclusive_host_lock():
            evidence["host_status"] = collector._daemon_request(shell, "STATUS").decode("ascii")
            version = collector._daemon_request(shell, "TMO 1000 SHL version").decode("ascii")
            evidence["version_reply"] = version
            if not version.startswith("OK ") or "w71c1" not in version or "5.02.0.V91" not in version:
                raise RuntimeError("not the verified fp 5.02 target")
            def read(name, value=None):
                return read_lens(shell, name, value, evidence["transcript"])
            p = read("getfpos")
            edge_distances = [read("getfedge", i) for i in (0, 1)]
            edge_positions = [read("cnvfpos", d) for d in edge_distances]
            evidence.update(cached_position_before=p, edge_distances_raw_inf_near=edge_distances,
                            edge_positions_inf_near=edge_positions)
            lo, hi = sorted(edge_positions)
            if not lo <= p - 100 < p + 100 <= hi:
                raise RuntimeError("current +/-100 is outside converted nominal edge range")
            positions = [p - 100, p, p + 100]
            distances = [read("cnvfdist", x) for x in positions]
            final_p = read("getfpos")
            evidence.update(cached_position_before=p, cached_position_after=final_p,
                            edge_distances_raw_inf_near=edge_distances,
                            edge_positions_inf_near=edge_positions,
                            conversion_positions=positions, conversion_distances_raw=distances,
                            cached_position_unchanged=p == final_p)
            finite = all(0 < d < 0x7FFFFFFF for d in distances)
            evidence["increasing_position_direction_from_table"] = (
                "nearer" if finite and distances[0] > distances[1] > distances[2] else
                "farther" if finite and distances[0] < distances[1] < distances[2] else "inconclusive")
            evidence["status"] = "readout-complete"
    except Exception as exc:
        evidence.update(status="readout-incomplete", error=repr(exc))
        raise
    finally:
        evidence["finished_at"] = dt.datetime.now().astimezone().isoformat()
        with args.output.open("x") as output:
            json.dump(evidence, output, indent=2)
            output.write("\n")
    print(args.output)
    print(json.dumps({k: v for k, v in evidence.items() if k not in ("transcript", "version_reply")}, indent=2))


if __name__ == "__main__":
    main()
