#!/usr/bin/env python3
"""Emit a review-only EP83 cold-boot candidate plan; never install or use USB."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


ROM_BASE = 0xC0000000
ROM_SHA256 = 'aaa5208a028d9c4aebb9cc8614add723d456e96b2a95914f433079954320e622'

# Ordered candidate edits.  These are evidence for review, not an installer.
PATCHES = (
    dict(sequence=1, name='native_mode2_in_success_noop', address=0xC01E5880,
         expected_before=0x4DF0E92D, candidate_after=0x47702000,
         meaning='Thumb `movs r0,#0; bx lr`; suppress native mode-2 IN before changing ctx3'),
    dict(sequence=2, name='ctx3_default_mode_bulk', address=0xC07E2800,
         expected_before=0x00000002, candidate_after=0x00000001,
         meaning='change the ctx3 default copied by C01E67F8 from mode 2 to mode 1'),
)


def project_root():
    for parent in Path(__file__).resolve().parents:
        if (parent / 'out/seg0_c0000000.bin').is_file():
            return parent
    raise ValueError('canonical seg0 ROM not found')


def _word(rom, address):
    offset = address - ROM_BASE
    if offset < 0 or offset + 4 > len(rom):
        raise ValueError(f'ROM does not cover 0x{address:08x}')
    return struct.unpack_from('<I', rom, offset)[0]


def build_plan(rom):
    """Verify one immutable ROM image and return a non-deployable JSON object."""
    digest = hashlib.sha256(rom).hexdigest()
    if digest != ROM_SHA256:
        raise ValueError('unsupported ROM hash')
    for patch in PATCHES:
        actual = _word(rom, patch['address'])
        if actual != patch['expected_before']:
            raise ValueError(
                f"unexpected before-image at 0x{patch['address']:08x}: 0x{actual:08x}")

    ordered = []
    for patch in PATCHES:
        item = dict(patch)
        item['address_hex'] = f"0x{patch['address']:08X}"
        item['expected_before_hex'] = f"0x{patch['expected_before']:08X}"
        item['candidate_after_hex'] = f"0x{patch['candidate_after']:08X}"
        ordered.append(item)

    return {
        'schema': 'fp-af-ep83-boot-plan-v1',
        'artifact_kind': 'review_only_patch_plan',
        'offline_only': True,
        'plan_only': True,
        'deployment_ready': False,
        'adapter_complete': False,
        'firmware_adapter_complete': False,
        'ownership_verified': False,
        'lifecycle_verified': False,
        'preflight_may_succeed': False,
        'autorun_generated': False,
        'card_write_performed': False,
        'usb_access_performed': False,
        'rom_sha256': digest,
        'rom_bytes': len(rom),
        'patch_order': ordered,
        'order_rule': 'install native sender suppression before changing the ctx3 default mode',
        'requires': {
            'new_explicit_authorization': True,
            'cold_boot': True,
            'usb_cable_unplugged_until_boot_patches_and_worker_are_ready': True,
            'existing_ep83_descriptor_bulk_patches': True,
            'one_serial_worker_task_owns_all_ep83_start_wait_trb_access': True,
            'explicit_dma_buffer_lease': True,
            'dma_alignment_bytes': 64,
            'post_attach_ctx3_tuple': [1, 1, 3, 0],
            'rollback_requires_reboot_without_candidate_patches': True,
        },
        'unresolved_blockers': [
            {
                'id': 'mode1_wait_completion_rearms_bulk_out',
                'source': 'blk_c01.c:138238-138258 (C01E7780)',
                'detail': ('mode-1 WaitIn completion can select the bulk OUT context with '
                           'C01E60E0, rewrite its TRB, and Start OUT when C31E3974!=1 and '
                           'C31E3A08==0; the EP01 worker-routing collision is not resolved'),
            },
            {
                'id': 'shared_worker_ptp_routing_not_closed',
                'source': 'fp_usb_shell/camera/worker.S and native PTP shared endpoint path',
                'detail': ('the existing worker/native routing lifecycle is still shared; the two '
                           'candidate words do not themselves establish a single owner'),
            },
            {
                'id': 'firmware_adapter_not_implemented',
                'source': 'highrate/af_sender.c callbacks',
                'detail': ('no fixed-address preflight/start/wait/completion binding is emitted, '
                           'and this plan must not be treated as permission to make one live'),
            },
        ],
        'rollback': {
            'live_restore_claimed': False,
            'method': 'cold reboot using a build without these candidate RAM-image edits',
        },
        'source_evidence': [
            'C01E5880 has source xrefs from C01E8158 and C01E91D0',
            'C07E2800 stores the ROM default ctx3 tuple {2,1,3,0}',
            'C01E67F8 copies the default tuple into the runtime endpoint context',
            'live read on 2026-09-16 confirmed ctx3 {2,1,3,0}; it did not authorize writes',
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path)
    parser.add_argument('--output', type=Path, required=True,
                        help='new local JSON file; never an AutoRun/card path')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('--output must not exist')
    rom_path = args.rom or project_root() / 'out/seg0_c0000000.bin'
    try:
        plan = build_plan(rom_path.read_bytes())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    try:
        with args.output.open('x', encoding='utf-8') as output:
            output.write(json.dumps(plan, indent=2, sort_keys=True) + '\n')
    except OSError as exc:
        parser.error(str(exc))
    print(json.dumps(plan, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
