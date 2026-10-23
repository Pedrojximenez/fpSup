"""Play the newest clip in camera and poll the LOSS playback counters (reads only).
usage: play_poll.py STATE_HEX OUT.csv [seconds]"""
import sys, time
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
import putfile as pf
PLAY = int(sys.argv[1], 16) + 0x49a4b4
out = open(sys.argv[2], 'w'); secs = float(sys.argv[3]) if len(sys.argv) > 3 else 15
names = ['seen','stock','decoded'] + [f'ref{i}' for i in range(12)] + ['last_us','max_us','buf','cap','got',
         'clips','ours','size_was','size_set','clip_failed','scr_bytes','scr_failed','scr_freed','scr_want','first_stock']
out.write('t,' + ','.join(names) + '\n')
def key(k):
    try: pf.sh(f'key {k}', retries=0, timeout_ms=3000)
    except Exception as e: print('key', k, e)
assert pf.sh('status get is_recording', retries=0, timeout_ms=3000).strip() == 'is_recording -> 0'
t0 = time.time()
key('PLAYON'); time.sleep(2.5); key('OKON'); time.sleep(0.3); key('OKOFF')
while time.time() - t0 < secs:
    try:
        w = pf.mem_get(PLAY, len(names))
    except Exception as e:
        print(f'{time.time()-t0:.1f} READ FAIL {e}'); break
    if not w: print(f'{time.time()-t0:.1f} READ None'); break
    line = f'{time.time()-t0:.2f},' + ','.join(str(x) for x in w)
    out.write(line + '\n'); out.flush()
    print(f'{time.time()-t0:5.1f} seen {w[0]} stock {w[1]} dec {w[2]} ref {[x for x in w[3:15]]} last {w[15]} max {w[16]} got {w[19]}')
    time.sleep(0.5)
