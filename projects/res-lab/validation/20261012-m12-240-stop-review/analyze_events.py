"""Offline lifecycle pairing for the current native diagnostic; no camera I/O."""
import importlib.util
import json
from pathlib import Path
import statistics

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('review_native_audit',
    HERE.parent / '20261011-virtual-rate-context-live/audit_recycle_path.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)
audit.HERE = HERE


def main():
    label = 'native-events-new-rule/logs-after'
    report = audit.analyze(label)
    report['limitations'] = [s for s in report['limitations'] if not s.startswith('These are earlier')]
    report['limitations'].append('Current SD diagnostic A001_117, not SSD or quiet SD A001_116. DEBUG timings cannot be used as a quiet-mode performance benchmark.')
    directory = HERE / label
    ring = json.loads((directory / 'RECMGR.json').read_text())
    phases = []
    for begin, end, name in ((0x10110304, 0x10110305, 'header_setup'),
                             (0x10110305, 0x10110306, 'header_build'),
                             (0x10110306, 0x10110307, 'header_copy')):
        starts = [r for r in ring if r['values'][0] == begin]
        ends = [r for r in ring if r['values'][0] == end]
        assert len(starts) == len(ends) == 104
        durations = [((b['timestamp'] - a['timestamp']) & 0xFFFFFFFF) / 1000
                     for a, b in zip(starts, ends)]
        phases.append({'phase': name, 'frames': len(durations),
                       'total_ms': sum(durations), 'median_ms': statistics.median(durations),
                       'maximum_ms': max(durations)})
    report['header_phases'] = phases
    report['nominal_frame_budget_ms'] = 1000 * 1001 / 240000
    before = report['before_vbuf']
    report['completed_notifications_still_waiting_at_vbuf'] = before['done_post'] - before['done_dispatch']
    first = report['frames'][0]
    report['first_frame'] = {
        'writer_call_return_ms': first['writer_return_ms'] - first['writer_enter_ms'],
        'writer_entry_to_completion_ms': first['complete_ms'] - first['writer_enter_ms'],
        'completion_notification_wait_ms': first['done_delay_ms'],
        'writer_entry_to_raw_release_branch_ms': first['raw_free_ms'] - first['writer_enter_ms'],
        'header_jobs_during_notification_wait': first['done_headers_between']}
    assert report['completed_notifications_still_waiting_at_vbuf'] == 5
    assert before['done_dispatch'] == before['raw_free'] == before['release_entry'] == 10
    assert report['counts']['prepare'] == report['counts']['completion'] == 104
    assert report['threads']['prepare'] == report['threads']['accepted_dispatch'] == report['threads']['done_dispatch']
    (HERE / 'native-lifecycle-analysis.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'before_vbuf': before, 'first_frame': report['first_frame'],
        'header_phases': phases, 'frame_budget_ms': report['nominal_frame_budget_ms']}, indent=2))


if __name__ == '__main__':
    main()
