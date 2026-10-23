"""Read the RECW wr_t (cached alias) on the camera: python3 -B recw_state.py [BASE]"""
import sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
import putfile as pf
import json, os, pathlib
# block from this boot's LOAD.LOG ("0A <block> ... 20RECW.BIN"); state_at from the build that is on the card
BLOCK = int(os.environ.get('RECW_BLOCK', '0x451BC5C0'), 0)
STATE_AT = json.loads((pathlib.Path(__file__).resolve().parents[2] / 'build/build.json').read_text())['state_at']
BASE = (BLOCK | 0x80000000) + STATE_AT          # cached alias
F = {'magic': 0, 'flag': 44, 'task_id': 48, 'block_bytes': 76, 'vol': 84, 'wvol': 88, 'sector_shift': 116}
C = ['n_install', 'n_refuse', 'n_send', 'n_stock_send', 'n_chunk', 'n_acq_retry', 'n_dev_err', 'n_wait_free',
     'n_drain', 'n_drain_timeout', 'n_late', 'n_late_direct', 'n_late_full', 'n_mismatch', 'last_status',
     'n_late_frame', 'ended_vol']   # the last two from build 0107f8d6 on (q moved +8)
F.update({c: 124 + 4 * i for i, c in enumerate(C)})
Q = 124 + 4 * len(C)
F.update({'q.carry': Q + 44, 'q.n_sealed': Q + 660, 'q.n_skip': Q + 664, 'q.n_late': Q + 668,
          'q.n_late_direct': Q + 672, 'q.n_chunks': Q + 676, 'q.n_full': Q + 680, 'q.n_mismatch': Q + 684})
def read():
    w = pf.mem_get(BASE, 0x380 // 4)
    assert None not in w
    return {k: w[o // 4] for k, o in F.items()}
if __name__ == '__main__':
    for k, v in read().items(): print(f'{k:16s} 0x{v:08X} {v}')
