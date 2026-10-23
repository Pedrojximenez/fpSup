"""One authorized native-DEBUG diagnostic, with the same installed BINs."""
import fcntl
import json
import re
import sys

from run_trial import capture, check, I, LCD
from native_events import Session


if __name__ == '__main__':
    assert re.fullmatch('[a-z0-9-]+', sys.argv[1])
    dest = I.HERE / sys.argv[1]
    dest.mkdir()
    proof = {'label': dest.name, 'target_seconds': 2, 'settings_changed': False,
             'native_debug_changes_scheduling': True, 'new_code_installed': False}
    save = lambda: (dest / 'trial.json').write_text(json.dumps(proof, indent=2) + '\n')
    session = Session(dest)
    with open('/tmp/fp-af-fusion.lock') as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            capture(dest, proof, save, session.prepare, session.finish)
            proof['after'] = I.inspect(dest / 'native-after.json')
            check(proof['after'])
            proof['lcd_after'] = LCD.shot(dest.name + '-after', dest)
            proof['phase'] = 'completed'
        except BaseException as exc:
            proof['error'] = type(exc).__name__ + ': ' + str(exc)
            raise
        finally:
            if session.mutated and not session.restored:
                session.restore()
            proof['logger_restored'] = session.restored
            save()
    print(proof['new_clips'], proof['record_log'], flush=True)
