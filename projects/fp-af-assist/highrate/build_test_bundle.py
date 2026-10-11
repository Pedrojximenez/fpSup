#!/usr/bin/env python3
"""Build a non-deployable, offline fp AF high-rate test bundle.

This program only reads a local ROM image, compiles local sources, and creates
a new output directory.  It contains no camera installer and performs no USB,
socket, device, card, process, or camera operation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

if __package__:
    from . import af_batch
    from . import build_publication
    from . import build_sender
else:
    import af_batch
    import build_publication
    import build_sender


BUNDLE_SCHEMA = "fp-af-highrate-offline-test-bundle-v1"
REQUEST_BYTES = 32
RESULT_BYTES = 32
OPS_BYTES = 24
VALID_PACKET_SIZES = (64, 512, 1024)


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _hex32(value):
    return f"0x{value:08X}"


def _address(name, value, alignment, size):
    if (type(value) is not int or not 0 < value <= 0xFFFFFFFF or
            value % alignment or value + size > 0x100000000):
        raise ValueError(f"invalid {name} address/alignment/span")


def _span(name, address, size, alignment):
    _address(name, address, alignment, size)
    return dict(name=name, address=address, address_hex=_hex32(address),
                end=address + size, end_hex=_hex32(address + size), bytes=size,
                alignment=alignment)


def _check_spans(spans):
    for span in spans:
        begin, end = span["address"], span["end"]
        if any(begin < protected_end and end > protected_begin
               for protected_begin, protected_end in build_publication.PROTECTED_RANGES):
            raise ValueError(f'{span["name"]} overlaps known live firmware code/source')
    for index, span in enumerate(spans):
        for other in spans[index + 1:]:
            if span["address"] < other["end"] and other["address"] < span["end"]:
                raise ValueError(f'{span["name"]} overlaps {other["name"]}')


def _verify_rom(path):
    path = Path(path)
    data = path.read_bytes()
    digest = _sha256(data)
    if digest != build_publication.ROM_SHA256:
        raise ValueError("unsupported ROM hash")
    offset = af_batch.CALLSITE - 0xC0000000
    if offset < 0 or offset + 4 > len(data):
        raise ValueError("ROM does not contain the audited callsite")
    if struct.unpack_from("<I", data, offset)[0] != af_batch.ORIGINAL_WORD:
        raise ValueError("unexpected original callsite word")
    return digest


def _readme(manifest):
    capture = manifest["capture"]
    layout = manifest["layout"]
    lines = [
        "SIGMA fp AF HIGH-RATE OFFLINE TEST BUNDLE",
        "",
        "NOT AF BETA. NOT HARDWARE VALIDATED. NOT DEPLOYMENT READY.",
        "NO CAMERA INSTALLER AND NO USB TRANSPORT ARE INCLUDED.",
        "",
        "The addresses below are explicit lab-model candidate inputs, not RAM leases.",
        "Do not write them to a camera from this bundle.",
        "",
        f"capacity: {capture['capacity']}",
        f"nonce: {capture['nonce_hex']}",
        f"maximum packet size: {manifest['transport']['max_packet_size']}",
        "",
        "candidate layout:",
    ]
    for span in layout:
        lines.append(f"  {span['name']}: {span['address_hex']}..{span['end_hex']} "
                     f"({span['bytes']} bytes)")
    lines += [
        "",
        "initial-capture.bin is an offline state+records concatenation, not an upload image.",
        "manifest.json records safety flags plus recorded source and artifact hashes.",
        "SHA256SUMS covers every emitted file except SHA256SUMS itself.",
        "SHA256SUMS is written last and is the bundle-complete marker.",
        "",
    ]
    return "\n".join(lines).encode()


def build_bundle(*, rom, recorder_base, sender_base, state_base, records_base,
                 dma_cpu_base, dma_bus_base, request_base, result_base, ops_base,
                 nonce, capacity, max_packet_size, veneer_base=None):
    """Return ``(artifact_bytes, manifest)`` without writing any file."""
    rom_sha256 = _verify_rom(rom)
    if type(max_packet_size) is not int or max_packet_size not in VALID_PACKET_SIZES:
        raise ValueError("max_packet_size must be 64, 512, or 1024")

    recorder, initial, publication = build_publication.assemble(
        code_base=recorder_base, state_base=state_base,
        records_base=records_base, capacity=capacity, nonce=nonce,
        veneer_base=veneer_base)
    sender, sender_assembly, sender_manifest = build_sender.assemble()
    records_bytes = capacity * af_batch.RECORD_BYTES
    dma_bytes = af_batch.BATCH_HEADER_BYTES + af_batch.HEADER_BYTES + records_bytes

    spans = [
        _span("recorder", recorder_base, len(recorder), 4),
        _span("sender", sender_base, len(sender), 4),
        _span("state", state_base, af_batch.HEADER_BYTES, 64),
        _span("records", records_base, records_bytes, 128),
        # The sender ABI requires a 64-byte-aligned DMA buffer. USB maximum
        # packet size controls host read sizing, not the camera DMA address.
        _span("dma_frame", dma_cpu_base, dma_bytes, 64),
        _span("request", request_base, REQUEST_BYTES, 4),
        _span("result", result_base, RESULT_BYTES, 4),
        _span("ops", ops_base, OPS_BYTES, 4),
    ]
    if veneer_base is not None:
        spans.append(_span("veneer", veneer_base, 8, 4))
    _check_spans(spans)
    _address("DMA bus", dma_bus_base, 64, dma_bytes)

    state = initial[:af_batch.HEADER_BYTES]
    records = initial[af_batch.HEADER_BYTES:]
    veneer = bytes.fromhex(publication["veneer_hex"])
    if len(state) != af_batch.HEADER_BYTES or len(records) != records_bytes:
        raise RuntimeError("publication builder returned an inconsistent capture image")
    if bool(veneer) != (veneer_base is not None):
        raise RuntimeError("publication builder returned an inconsistent veneer")
    if veneer and (len(veneer) != 8 or
                   struct.unpack("<2I", veneer) != (0xE51FF004, recorder_base) or
                   publication["candidate_branch_word"] !=
                   build_publication.branch_word(veneer_base)):
        raise RuntimeError("publication builder returned an invalid veneer")

    manifest = {
        "schema": BUNDLE_SCHEMA,
        "kind": "offline_test_bundle",
        "label": "NOT_AF_BETA",
        "safety": {
            "offline_only": True,
            "deployment_ready": False,
            "hardware_validated": False,
            "af_beta": False,
            "camera_installer_included": False,
            "usb_transport_included": False,
            "firmware_adapter_complete": False,
            "ownership_verified": False,
            "lifecycle_verified": False,
            "dma_mapping_verified": False,
            "cache_publication_verified": False,
        },
        "warnings": [
            "Candidate addresses are explicit lab-model inputs, not RAM leases.",
            "The optional veneer has separate ownership and cache requirements.",
            "This bundle must not be described as an AF beta or installed on a camera.",
        ],
        "address_provenance": "explicit_unleased_lab_model_inputs",
        "firmware": {
            "target": "SIGMA fp Ver.5.02",
            "rom_sha256": rom_sha256,
            "callsite": af_batch.CALLSITE,
            "callsite_hex": _hex32(af_batch.CALLSITE),
            "expected_original_word": af_batch.ORIGINAL_WORD,
            "expected_original_word_hex": _hex32(af_batch.ORIGINAL_WORD),
            "candidate_branch_word": publication["candidate_branch_word"],
            "candidate_branch_word_hex": _hex32(publication["candidate_branch_word"]),
        },
        "capture": {
            "nonce": nonce,
            "nonce_hex": _hex32(nonce),
            "capacity": capacity,
            "record_bytes": af_batch.RECORD_BYTES,
            "state_bytes": af_batch.HEADER_BYTES,
            "records_bytes": records_bytes,
            "capture_bytes": len(initial),
            "batch_bytes": dma_bytes,
            "initial_capture_representation":
                "offline_concat_state_then_records_not_uploadable",
        },
        "transport": {
            "endpoint": 0x83,
            "physical_endpoint": 7,
            "logical_endpoint": 3,
            "max_packet_size": max_packet_size,
            "dma_cpu_base": dma_cpu_base,
            "dma_cpu_base_hex": _hex32(dma_cpu_base),
            "dma_bus_base": dma_bus_base,
            "dma_bus_base_hex": _hex32(dma_bus_base),
            "dma_mapping_verified": False,
        },
        "layout": spans,
        "publication": publication,
        "sender": sender_manifest,
        "inputs": {
            "bundle_builder_sha256": _sha256(Path(__file__).read_bytes()),
            "format_source_sha256": _sha256(Path(af_batch.__file__).read_bytes()),
            "publication_builder_sha256": _sha256(
                Path(build_publication.__file__).read_bytes()),
            "sender_builder_sha256": _sha256(
                Path(build_sender.__file__).read_bytes()),
        },
    }

    artifacts = {
        "README.txt": b"",  # Filled after the exact manifest layout exists.
        "initial-capture.bin": initial,
        "initial-records.bin": records,
        "initial-state.bin": state,
        "publication.bin": recorder,
        "sender-core.S": sender_assembly.encode(),
        "sender-core.bin": sender,
    }
    if veneer:
        artifacts["veneer.bin"] = veneer
    artifacts["README.txt"] = _readme(manifest)
    manifest["artifacts"] = {
        name: {"bytes": len(data), "sha256": _sha256(data)}
        for name, data in sorted(artifacts.items())
    }
    return artifacts, manifest


def write_bundle(output, **kwargs):
    """Create one new bundle directory; refuse every pre-existing path."""
    output = Path(output)
    if os.path.lexists(output):
        raise FileExistsError(f"output already exists: {output}")
    artifacts, manifest = build_bundle(**kwargs)
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    files = dict(artifacts, **{"manifest.json": manifest_bytes})
    sums = "".join(f"{_sha256(files[name])}  {name}\n" for name in sorted(files)).encode()

    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(exist_ok=False)
    # Payloads first, manifest next, checksum last.  A write fault therefore
    # cannot leave the completion marker in an incomplete directory.
    for name, data in sorted(artifacts.items()):
        (output / name).write_bytes(data)
    (output / "manifest.json").write_bytes(manifest_bytes)
    (output / "SHA256SUMS").write_bytes(sums)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--rom", type=Path,
                        default=build_publication.root() / "out/seg0_c0000000.bin")
    for name in ("recorder-base", "sender-base", "state-base", "records-base",
                 "dma-cpu-base", "dma-bus-base", "request-base", "result-base",
                 "ops-base", "nonce"):
        parser.add_argument("--" + name, required=True, type=lambda value: int(value, 0))
    parser.add_argument("--capacity", required=True, type=int)
    parser.add_argument("--max-packet-size", required=True, type=int,
                        choices=VALID_PACKET_SIZES)
    parser.add_argument("--veneer-base", type=lambda value: int(value, 0))
    args = parser.parse_args(argv)
    values = vars(args)
    output = values.pop("output")
    try:
        manifest = write_bundle(output, **values)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "output": str(output),
        "schema": manifest["schema"],
        "label": manifest["label"],
        "deployment_ready": manifest["safety"]["deployment_ready"],
        "hardware_validated": manifest["safety"]["hardware_validated"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
