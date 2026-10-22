"""Read-only provenance audit of the user's successful SSD sequence.

Only selected, relevant historical records are retained. Historical tool calls
are evidence, never executed. This does not identify an exact installed binary,
reinstall an obsolete loader, or establish the early-stop root cause.
"""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = HERE / "success-version-audit"
CLIP = Path("/Users/dido/Movies/fpsup/hightspeed/A001_193")
HISTORY = Path("/Users/dido/.claude/projects/"
               "-Users-dido-Developer-localized-SIGMAfp-re-projects-open-gate/"
               "5acbf12f-3568-4c49-9959-d190b5001045.jsonl")
SELECTED = {
    2721: "H2 predecessor donor selection: p13 and fill",
    2739: "H2 verified live install before the aspect correction",
    2744: "Actual H2 live recipe, 25 canvas pairs, firmware model",
    2834: "First screenshot capture bounded by historical host tool call",
    2840: "H2 verified live install with corrected aspect, 08:55 local",
    2915: "Contemporaneous summary: sensor 240, native application 30",
    3050: "First new rate-hook installation attempt after the clip time",
    3051: "Installation preflight failed, zero writes",
    3065: "Contemporaneous report that the previous H2 install remained",
    3160: "Second screenshot capture bounded by historical host tool call",
    3161: "Second screenshot capture completion",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def plain(record):
    content = record.get("message", {}).get("content", "")
    if isinstance(content, str):
        return content
    parts = []
    for block in content:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif block.get("type") == "tool_result" and isinstance(block.get("content"), str):
            parts.append(block["content"])
        elif block.get("type") == "tool_use":
            parts.append("Historical tool input (not executed): " + json.dumps(
                {"name": block.get("name"), "input": block.get("input")},
                ensure_ascii=False))
    return "\n".join(parts)


def images(value):
    if isinstance(value, dict):
        if value.get("type") == "image":
            source = value.get("source", {})
            if source.get("type") == "base64":
                yield source
        else:
            for child in value.values():
                yield from images(child)
    elif isinstance(value, list):
        for child in value:
            yield from images(child)


def exif(paths):
    args = ["/opt/homebrew/bin/exiftool", "-j", "-G1", "-a", "-s",
            "-time:all", "-Software", "-Model", "-Make", "-SerialNumber",
            "-FrameRate", "-ImageWidth", "-ImageHeight", "-ExposureTime",
            "-ISO", "-Compression", "-DefaultCropSize", "-DefaultCropOrigin"]
    run = subprocess.run(args + [str(p) for p in paths], check=True,
                         capture_output=True, text=True)
    result = json.loads(run.stdout)
    for row in result:
        # Host reads change these fields; they do not date the recording.
        row.pop("System:FileAccessDate", None)
        row.pop("System:FileInodeChangeDate", None)
    return result


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    OUT.mkdir(exist_ok=True)
    originals = [CLIP / ("A001_193_20260929_%06d.DNG" % n)
                 for n in (1, 2405, 4809)]
    originals += [CLIP / "A001_193_20260929.WAV", CLIP / "SPP_metadata.xmp"]
    current = HERE / "ssd-240-sensorlab-v15-manual/ssd-files/A001_276_20261011_000001.DNG"
    metadata = exif(originals + [current])
    assert all(row["ExifIFD:DateTimeOriginal"] == "2026:09:29 09:14:25"
               for row in metadata[:3])
    assert metadata[3]["RIFF:DateTimeOriginal"] == "2026:09:29 09:14:25"
    write("metadata.json", metadata)
    stats = []
    for p in originals:
        stat = p.stat()
        stats.append({"path": str(p), "bytes": stat.st_size,
                      "sha256": digest(p.read_bytes()),
                      "mtime": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(),
                      "birthtime": datetime.fromtimestamp(stat.st_birthtime).astimezone().isoformat()})
    write("original-file-stat.json", stats)

    selected, screenshots = [], []
    import base64
    with HISTORY.open() as stream:
        for line_number, line in enumerate(stream, 1):
            if line_number not in SELECTED and line_number not in (2848, 3168):
                continue
            record = json.loads(line)
            if line_number in SELECTED:
                selected.append({"source": str(HISTORY), "line": line_number,
                                 "source_line_sha256": digest(line.encode()),
                                 "timestamp_utc": record.get("timestamp"),
                                 "purpose": SELECTED[line_number], "text": plain(record)})
            else:
                for source in images(record.get("message", {}).get("content", [])):
                    assert source["media_type"] == "image/jpeg"
                    data = base64.b64decode(source["data"], validate=True)
                    destination = OUT / ("historical-screen-%d.jpg" % line_number)
                    destination.write_bytes(data)
                    screenshots.append({"source": str(HISTORY), "line": line_number,
                                        "host_read_timestamp_utc": record.get("timestamp"),
                                        "path": str(destination), "bytes": len(data),
                                        "sha256": digest(data)})
    assert len(selected) == len(SELECTED)
    write("historical-relevant-records.json", selected)
    write("historical-screenshots.json", screenshots)
    clock = None
    if screenshots:
        screen_metadata = exif([Path(row["path"]) for row in screenshots])
        write("historical-screen-metadata.json", screen_metadata)
        assert len(screen_metadata) == 2
        serial = metadata[0]["Sigma:SerialNumber"]
        assert all(row["Sigma:SerialNumber"] == serial for row in metadata[:3] + screen_metadata)
        intervals = []
        records = {row["line"]: row for row in selected}
        for row, (before, after) in zip(screen_metadata, ((2834, 2840), (3160, 3161))):
            # Capture JPEG's OffsetTime is zero/default, DateTimeOriginal is
            # invalid. Compare its ModifyDate wall time with host +08:00;
            # do not interpret the JPEG composite timestamp as actual UTC.
            wall = datetime.strptime(row["IFD0:ModifyDate"], "%Y:%m:%d %H:%M:%S")
            host_before = datetime.fromisoformat(records[before]["timestamp_utc"].replace("Z", "+00:00"))
            host_after = datetime.fromisoformat(records[after]["timestamp_utc"].replace("Z", "+00:00"))
            from datetime import timedelta, timezone
            local = timezone(timedelta(hours=8))
            a = host_before.astimezone(local).replace(tzinfo=None)
            b = host_after.astimezone(local).replace(tzinfo=None)
            intervals.append({"host_start": host_before.isoformat(), "host_end": host_after.isoformat(),
                              "camera_wall_time": wall.isoformat(),
                              "camera_ahead_seconds": [(wall - b).total_seconds(), (wall - a).total_seconds() + 1.0]})
        lower = max(row["camera_ahead_seconds"][0] for row in intervals)
        upper = min(row["camera_ahead_seconds"][1] for row in intervals)
        assert 0 < lower <= upper < 120
        camera_start = datetime.fromisoformat("2026-09-29T09:14:25+08:00")
        clock = {"same_camera_serial": serial, "capture_windows": intervals,
                 "intersected_camera_ahead_seconds": [lower, upper],
                 "inferred_clip_host_local_start_range": [(camera_start - timedelta(seconds=upper)).isoformat(),
                                                           (camera_start + timedelta(seconds=1-lower)).isoformat()],
                 "assumptions": "Same camera clock and +08:00 wall-time setting across two nearby captures. Capture occurs between host tool start and successful result. Integer timestamp granularity included.",
                 "caveat": "Bounded historical clock inference; no independent oscillator calibration or exact recorded-frame timestamp."}
        write("historical-clock-correlation.json", clock)

    # Independent old runtime evidence: do not derive expectations from v15.
    live = next(row["text"] for row in selected if row["line"] == 2744)
    pairs = {int(off, 16): int(value) for off, value in re.findall(
        r"^\s+\+0x([0-9A-Fa-f]+) = (\d+)", live, re.MULTILINE)}
    assert len(pairs) == 25 and 0x88 not in pairs
    profiles_path = ROOT / "research/other/external/FP3K-technical-handoff-2026-09-10/analysis/firmware/raw-profiles.json"
    profile_blob = profiles_path.read_bytes()
    profiles = json.loads(profile_blob)
    rows = {pid: next(row["words"] for row in profiles["rows"] if pid in row["profile_ids"])
            for pid in (13, 83)}
    canvases = {}
    for pid, row in rows.items():
        result = list(row)
        for off, value in pairs.items():
            result[off // 4] = value
        canvases[pid] = result
    differences = {hex(i * 4): [a, b] for i, (a, b) in enumerate(
        zip(canvases[13], canvases[83])) if a != b and i * 4 != 0x30}
    assert differences == {"0x88": [0, 4]}
    write("historical-h2-profile-difference.json", {
        "source": "Actual archived 25-pair H2 live readback applied to independent native profile defaults",
        "profiles_source": str(profiles_path), "profiles_sha256": digest(profile_blob),
        "runtime_pairs": {hex(off): value for off, value in pairs.items()},
        "p13_vs_p83_after_runtime_pairs_excluding_fps_latch": differences,
        "engine_fps_word_excluded": "Both paths replace +0x30 from FPSLATCH. No full 65-word canvas snapshot of A001_193 is available.",
        "early_stop_root_cause_established": False,
        "hardware_changes_made": False})

    write("conclusion.json", {
        "clip": str(CLIP), "camera_recording_start": "2026-09-29T09:14:25+08:00",
        "last_frame_file_time": "2026-09-29T09:14:46+08:00",
        "date_confirmation": "First/middle/last internal DNG EXIF, WAV RIFF and original filesystem timestamps agree",
        "likely_version_family": "September 29 H2 RAM prototype, before the new DNG rate hook was successfully installed",
        "evidence": ["08:55 local verified H2 install, M12 and complete 27-word recipe agreement",
                     "09:14 camera clip time falls before 09:16 host first new rate-hook install attempt",
                     "09:16 install failed in preflight with zero writes; old H2 was reported retained",
                     "1008x672 / 992x662 / 12-bit / FrameRate30000/1001 agrees with this predecessor"],
        "historical_clock_correlation": clock,
        "exact_binary_or_commit_identified": False,
        "r10_is_exact_successful_clip_version": False,
        "r10_status": "A different later success reference, built October 1; not the September 29 clip provenance",
        "new_difference": "Historical H2 used native p13, leaving PARAM+0x88=0; r10's p83 leaves it at4",
        "limitations": "No archived record explicitly names this exact September29 A001_193 take, no embedded custom build hash found in examined standard tags, and no full recorded canvas/installed binary snapshot at the clip time. This is a strongly supported version-family inference, not exact binary identification or a proven repair."})
    print(json.dumps({"output": str(OUT), "historical_records": len(selected),
                      "screenshots": len(screenshots), "profile_difference": differences,
                      "exact_version_identified": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
