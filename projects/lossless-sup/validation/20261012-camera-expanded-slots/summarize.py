"""Offline reduction of immutable trial evidence; never connects to a camera."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def trial(label):
    d = json.loads((HERE / (label + '.json')).read_text())
    s = d['after']
    v = s['values']
    req, fin = map(int, re.search(r'req_cnt=(\d+), fin_cnt=(\d+),', d['record_log']).groups())
    return {
        'evidence': label + '.json', 'clip': d['new_clips'][0],
        'boot': s['boot'],
        'raw_geometry': [v['rec.facts.seen.width'], v['rec.facts.seen.height']],
        'bit_depth': v['rec.facts.seen.bits'],
        'fps': [v['rec.facts.seen.fps_num'], v['rec.facts.seen.fps_den']],
        'active_at_end_of_window': d['active_at_end_of_window'],
        'stop_reason': 'mem, raw2' if 'mem, raw2' in d['record_log'] else 'button',
        'arrivals': v['take_frames'], 'requested': req, 'finished': fin,
        'compressed_written': v['bulk_policy.compressed'], 'raw_written': v['bulk_policy.raw'],
        'discarded': v['record_diag.discard_count'],
        'active_slots': s['capacity'], 'free_slots_after': s['descriptors_free'],
        'registry_occupied_after': s['registry_occupied'],
        'registry_count_after': s['registry_count'], 'registry_lock_after': s['registry_lock'],
        'completion_cookies_pending_after': [v[f'slots.cookies[{i}].pending'] for i in range(2)],
        'writer_idle_after': s['idle'],
        'codec_stalls': v['hold.stalls'] + v['hold_b.stalls'],
        'stale_commits': v['hold.stale_commits'] + v['hold_b.stale_commits'],
        'native_bulk_bytes': int(re.search(r'bulk-size=(\d+)', d['record_log'])[1]),
        'extra_count_flushes': v['bulk_policy.count_flushes'],
        'extra_pressure_flushes': v['bulk_policy.pressure_flushes'],
        'completion_budget_after_us': v['slots.completion_budget_us'],
        'slot_plans_refused': v['slots.refused'],
    }


if __name__ == '__main__':
    labels = ['fhd30-on-01', 'fhd60-on-01'] + [f'reslab3k-stop-{n:02}' for n in range(1, 11)]
    trials = [trial(label) for label in labels]
    for t in trials:
        assert t['requested'] == t['finished']
        assert t['arrivals'] == t['finished'] + t['discarded']
        assert t['compressed_written'] + t['raw_written'] == t['finished']
        assert t['free_slots_after'] == t['active_slots']
        assert not any([t['registry_occupied_after'], t['registry_count_after'], t['registry_lock_after'],
                        *t['completion_cookies_pending_after'], *t['writer_idle_after'].values()])
        assert t['native_bulk_bytes'] == 64 * 1024 * 1024
        assert t['extra_count_flushes'] == t['extra_pressure_flushes'] == 0
    stress = trials[2:]
    recovered = trial('fhd60-manual-stop-recovered')
    assert recovered['boot'] == trials[0]['boot']
    assert recovered['arrivals'] == recovered['requested'] == recovered['finished'] == 16911
    assert recovered['free_slots_after'] == recovered['active_slots'] == 428
    assert not any([recovered['registry_occupied_after'], recovered['registry_count_after'],
                    recovered['registry_lock_after'], *recovered['completion_cookies_pending_after'],
                    *recovered['writer_idle_after'].values()])
    samples = [json.loads(p.read_text()) for p in sorted(HERE.glob('*-frames/validation.json'))]
    report = {
        'verdict': 'do_not_promote_high_rate_stability_failed',
        'artifact': json.loads((HERE / 'artifact.json').read_text()),
        'trials': trials,
        'ten_auto_stops': {
            'count': len(stress), 'same_boot': len({t['boot'] for t in trials}) == 1,
            'arrivals': sum(t['arrivals'] for t in stress),
            'finished': sum(t['finished'] for t in stress),
            'discarded': sum(t['discarded'] for t in stress),
            'all_tracked_ownership_released': True,
        },
        'last_take_incident': {
            'evidence': 'fhd60-after-ten-stops.json',
            'recovery_evidence': 'fhd60-manual-stop-recovered.json',
            'measurement': recovered,
            'intended_window_seconds': 25,
            'actual_duration_seconds': None,
            'actual_capture_facts': {'raw_geometry': recovered['raw_geometry'], 'fps': recovered['fps'], 'bits': recovered['bit_depth']},
            'host_stop_key_sent': False,
            'user_observed': 'Still recording; seconds indicator very laggy; live picture normal.',
            'manual_stop_confirmed_by_user': True,
            'write_lamp_off_and_menus_normal_confirmed_by_user': True,
            'usb_after_manual_stop': 'timeout; recovered after USB replug without reboot',
            'post_take_slot_recovery': 'verified in same boot before file reads or reboot',
            'files_and_final_counts': 'A001_130; native req=fin=16911; take_frames=16911; no recorded discards',
            'record_log_batch_detail': 'truncated with non-text suffix; header counts corroborated by state',
        },
        'dng_samples': {'count': sum(len(s['frames']) for s in samples), 'reports': samples,
                        'incomplete': 'A001_130 frame 8456 read timed out; middle and final frame not decoded'},
        'file_read_incident': {
            'evidence': 'fhd60-manual-stop-recovered-frames/008456.read.log',
            'getfile_echo_result': 'LIBUSB_ERROR_TIMEOUT; uncertain read outcome',
            'separate_from_recording_test': True,
            'cleanup_risk': 'getfile.py ERR exit precedes heap-buffer finally; subsequent sample overwrote shared parameters',
            'leaked_bytes': None,
            'recovery': 'one idle-guarded normal reboot, reboot-02-recovery.json',
        },
        'limits': [
            'Tracked descriptors, registry and completion cookies are not a whole-heap leak audit.',
            'A completed writer queue does not imply every captured frame was retained.',
            'No root cause established for lag or USB timeouts; STOPFX causality not isolated.',
            'No controlled same-scene A/B against the earlier early-flush build.',
            'Only four DNG samples decoded; the long take middle and end remain unverified.',
            'No exact wall-clock recording duration or all-frame timestamp continuity established.',
            'The file-transfer timeout may leave an allocation; its address/size cannot now be safely established.',
        ],
    }
    final = HERE / 'final-standby.json'
    if final.exists():
        report['final_camera_state'] = json.loads(final.read_text())
    (HERE / 'status.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'verdict': report['verdict'], 'ten_auto_stops': report['ten_auto_stops']}))
