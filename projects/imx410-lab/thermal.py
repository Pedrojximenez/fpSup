#!/usr/bin/env python3
"""Sensor / body temperature over the shell (`adc temp_cmos`, `adc temp_battery`; the sensor temperature is an ADC
channel, not a sensor register). The user asked (2026-10-23) to watch the sensor temperature: the camera has been
running hot during the long batches and the shell wedges might be thermal.

    thermal.py              print both readings
    thermal.py log FILE     append one JSON line (time + readings) -- the batches call log() before every config
Library: read() -> {'cmos': value or None, 'battery': ..., 'raw': {...}}; wait_cool(limit, poll) blocks while hot.
"""
import json, re, sys, time, pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

LIMIT = None          # set once the units / normal range are known (first readings, 2026-10-23)


def _num(text):
    # reply line: '<raw ADC value> :     0 ms' -- the raw 8-bit ADC reading (unit unknown, 2026-10-23)
    m = re.search(r'(-?\d+)\s*:\s*\d+\s*ms', text)
    return float(m.group(1)) if m else None


TEMP_C = 0xC34258CC   # firmware's own readings, 0.1 degC: body, cmos, lcd, battery (TempChk, notes/THERMAL.md)
LIMIT_C = 52.0        # our pause line: below the camera's cmos warning (56.0) and shutdown (64.0) -- the camera's
                      # TempChk thread runs in every state, but its warning only shows an icon and never stops us


def read_c():
    import bufa_probe as B
    v = B.P().mem_get(TEMP_C, 4)
    if not v or None in v:
        return None
    def c(x):
        x = x - (1 << 32) if x >= 1 << 31 else x
        return x / 10.0
    return dict(body=c(v[0]), cmos=c(v[1]), lcd=c(v[2]), battery=c(v[3]))


def read():
    import bufa_probe as B
    raw, out = {}, {}
    for k, ch in (('cmos', 'temp_cmos'), ('body', 'temp_body'), ('battery', 'temp_battery'), ('lcd', 'temp_lcd')):
        try:
            t = B.P().sh(f'adc {ch}').strip()
        except Exception as e:                  # noqa: BLE001 -- a read failure must not stop a batch
            t = f'ERR {e}'
        raw[k] = t[-200:]
        out[k] = _num(t)
    out['raw'] = raw
    try:
        out['C'] = read_c()
    except Exception:                               # noqa: BLE001
        out['C'] = None
    return out


def log(path, tag=''):
    r = read()
    with open(path, 'a') as f:
        f.write(json.dumps(dict(t=time.strftime('%H:%M:%S'), tag=tag, cmos=r['cmos'], body=r['body'], battery=r['battery'], lcd=r['lcd'], C=r.get('C'))) + '\n')
    return r


BASE_FILE = HERE / 'captures' / 'thermal_base.json'
DRIFT = 25            # until the conversion is known: pause when the sensor ADC moved this far from the run's start


def wait_cool(limit=None, poll=30, max_wait=1800):
    limit = limit if limit is not None else LIMIT_C
    r = read()
    if r.get('C'):                                  # absolute guard in degC (firmware conversion, THERMAL.md)
        t0 = time.time()
        while r.get('C') and r['C']['cmos'] >= limit and time.time() - t0 < max_wait:
            print(f"  sensor {r['C']['cmos']:.1f} C >= {limit} C: cooling", flush=True)
            time.sleep(poll); r = read()
        return r
    if True:                                        # no degC reading: relative guard on the raw ADC                               # relative guard against the value at the start of the run
        r = read()
        if r['cmos'] is None:
            return r
        if not BASE_FILE.exists():
            BASE_FILE.write_text(json.dumps(dict(cmos=r['cmos'], t=time.strftime('%H:%M:%S'))))
            return r
        base = json.loads(BASE_FILE.read_text())['cmos']
        t0 = time.time()
        while r['cmos'] is not None and abs(r['cmos'] - base) > DRIFT and time.time() - t0 < max_wait:
            print(f'  sensor ADC {r["cmos"]} vs start {base}: cooling', flush=True)
            time.sleep(poll); r = read()
        return r
    t0 = time.time()
    while True:
        r = read()
        if r['cmos'] is None or r['cmos'] < limit or time.time() - t0 > max_wait:
            return r
        print(f'  sensor {r["cmos"]} >= {limit}: cooling', flush=True)
        time.sleep(poll)


if __name__ == '__main__':
    if len(sys.argv) > 2 and sys.argv[1] == 'log':
        print(log(sys.argv[2]))
    else:
        r = read()
        print('cmos', r['cmos'], '| battery', r['battery'])
        for k, v in r['raw'].items():
            print(f'  {k}: {v}')
