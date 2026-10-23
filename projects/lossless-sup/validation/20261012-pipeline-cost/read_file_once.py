"""Reviewed getfile entrypoint with one bounded execution, never echo retries.

Only an idle, locked parent may invoke this. A failed read stops that parent;
do not reuse its parameter block until worker quiescence/ownership is known.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'fpSup/fp_usb_shell'))
import getfile

_sh = getfile.sh


def single_sh(command, **kwargs):
    kwargs['retries'] = 0
    kwargs['timeout_ms'] = 10000
    return _sh(command, **kwargs)


getfile.sh = single_sh
if __name__ == '__main__':
    sys.exit(getfile.main())
