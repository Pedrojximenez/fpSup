#!/usr/bin/env python3
"""Run original df101fh VID selection and numeric dispatch, never USB/device I/O.

The original shared camera task receives one synthetic action. Driver selection
is executed from original firmware; camera initialization is not. Ready state,
queue ownership, clock, locks and logger are explicit fixtures.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

P = Path(__file__).resolve().parents[1]
W = P.parent.parent
sys.path.insert(0, str(W / 'dji_focus_pro/tools'))
import verify_focus_handle_ptp as base
import unicorn as uc
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR

META, OPS, TASK_OPS, READY = 0x20201608, 0x20201670, 0x202109A4, 0x2022D278
LOG, QUEUE, SCHEDULER = 0x600E3278, 0x600E3420, 0x6009A614


def main():
    out = Path(sys.argv[1])
    assert not out.exists()
    raw = base.IMAGE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == base.SHA
    executed = {}

    def original(address, size):
        if 0x60030000 <= address < 0x60030000 + len(raw):
            offset = address - 0x60030000
        else:
            src, dst, length = next(c for c in base.COPIES if c[1] <= address and address+size <= c[1]+c[2])
            offset = src-0x60030000+address-dst
        return offset, raw[offset:offset+size]

    def record(m, address, size):
        offset, b = original(address, size)
        assert bytes(m.mem_read(address, size)) == b
        row = dict(address=hex(address), file_offset=offset, hex=b.hex())
        if address in executed:
            assert executed[address] == row
        executed[address] = row

    def word(m, addr):
        return struct.unpack('<I', m.mem_read(addr, 4))[0]

    def ret(m, value=0, high=None):
        m.reg_write(UC_ARM_REG_R0, value)
        if high is not None:
            m.reg_write(UC_ARM_REG_R1, high)
        m.reg_write(UC_ARM_REG_PC, m.reg_read(UC_ARM_REG_LR))

    def run(m, entry):
        m.reg_write(UC_ARM_REG_LR, base.RETURN | 1)
        m.emu_start(entry | 1, base.RETURN, count=50000)

    def select(vid, pid):
        m = base.machine()
        logs = []
        def hook(_m, address, size, _user):
            if address == LOG:
                logs.append(m.reg_read(UC_ARM_REG_R0)); ret(m); return
            record(m, address, size)
        handle = m.hook_add(uc.UC_HOOK_CODE, hook)
        m.reg_write(UC_ARM_REG_R0, vid)
        m.reg_write(UC_ARM_REG_R1, pid)
        run(m, 0x600943A4)
        assert m.reg_read(UC_ARM_REG_PC) == base.RETURN
        accepted = m.reg_read(UC_ARM_REG_R0)
        kind = bytes(m.mem_read(META+0x14, 1))[0]
        if accepted:
            m.reg_write(UC_ARM_REG_R0, 0x12345678)  # host-handle fixture, stored only
            run(m, 0x600942DC)
            assert m.reg_read(UC_ARM_REG_PC) == base.RETURN
        m.hook_del(handle)
        return m, dict(vid=hex(vid), pid=hex(pid), accepted=accepted, kind=kind,
                       selected_ops_hex=bytes(m.mem_read(OPS, 40)).hex(),
                       ioctl=hex(word(m, OPS+0x20)), logger_calls=len(logs))

    classifier = []
    for vid, pid, accept, kind, ioctl in [
        (0x1003, 0x1234, 1, 8, 0x600D7243),
        (0x1003, 0x5678, 1, 8, 0x600D7243),
        (0x04DA, 0x1234, 1, 4, 0x60096205),
        (0xFFFF, 0x1234, 0, 0, 0x600941D5),
    ]:
        m, result = select(vid, pid)
        assert (result['accepted'],result['kind'],int(result['ioctl'],16)) == (accept,kind,ioctl)
        classifier.append(result)

    cases = []
    configs = [
        ('sigma_ready', 0x1003, 1, True, 0),
        ('panasonic_ready', 0x04DA, 1, True, 0),
        ('panasonic_not_ready', 0x04DA, 0, True, 0),
        ('no_ops', 0x04DA, 1, False, 0),
        ('queue_failure', 0x04DA, 1, True, -1),
    ]
    for name, vid, ready, have_ops, queue_return in configs:
        m, selection = select(vid, 0x1234)
        m.mem_write(TASK_OPS, struct.pack('<I', OPS if have_ops else 0))
        m.mem_write(READY, bytes([ready]))
        # Same initialized PTP bookkeeping as the earlier packet-builder test.
        # No session or device handshake is executed in this experiment.
        m.mem_write(base.HOST, struct.pack('<II', 0x1234, 1))
        m.mem_write(base.HOST+0x7938, struct.pack('<I', 1))
        m.mem_write(base.HOST+0x7930, b'\0')
        m.mem_write(0x202117D0, b'\0'*8)
        state = dict(name=name, selection=selection, ready_fixture=ready,
                     ops_pointer_fixture=hex(OPS) if have_ops else None,
                     queue_return_fixture=queue_return, action_hex=struct.pack('<II',0x12,1000).hex(),
                     queue_calls=0, dispatcher_calls=[], dispatcher_returns=[], boundary_calls=[],
                     packets=None, stopped_at=None)
        def hook(_m, address, size, _user):
            if address == QUEUE:
                state['queue_calls'] += 1
                assert m.reg_read(UC_ARM_REG_R0) == 0x202114FC
                if state['queue_calls'] == 2:
                    state['stopped_at'] = 'next_queue_receive'
                    m.emu_stop(); return
                if queue_return == 0:
                    m.mem_write(m.reg_read(UC_ARM_REG_R1), struct.pack('<II',0x12,1000))
                ret(m, queue_return & 0xFFFFFFFF); return
            if address in (0x600D7242, 0x60096204):
                state['dispatcher_calls'].append(dict(entry=hex(address),
                    selector=m.reg_read(UC_ARM_REG_R1), value=m.reg_read(UC_ARM_REG_R2)))
            if address == 0x60093A16:
                state['dispatcher_returns'].append(m.reg_read(UC_ARM_REG_R0))
            if address in (LOG, 0x6009416C, 0x60094180, 0x3AC2C):
                state['boundary_calls'].append(hex(address)); ret(m); return
            if address == 0x600D6F4A:
                state['boundary_calls'].append('clock=1000000'); ret(m,1000000,0); return
            if address == SCHEDULER:
                state['packets'] = {}
                for label, offset in [('command',0x44), ('data',0xD0)]:
                    n = word(m,base.HOST+offset)
                    state['packets'][label] = bytes(m.mem_read(base.HOST+offset,n)).hex()
                state['stopped_at'] = 'before_usb_scheduler'
                m.emu_stop(); return
            record(m, address, size)
        m.hook_add(uc.UC_HOOK_CODE,hook)
        run(m,0x60093890)
        assert state['stopped_at'] is not None, (name,hex(m.reg_read(UC_ARM_REG_PC)))
        if name == 'sigma_ready':
            assert state['dispatcher_calls'] == [dict(entry='0x600d7242',selector=32,value=1000)]
            assert state['dispatcher_returns'] == [3] and state['packets'] is None
            assert not state['boundary_calls'], state
        elif name == 'panasonic_ready':
            assert state['dispatcher_calls'] == [dict(entry='0x60096204',selector=32,value=1000)]
            assert state['packets'] == dict(command='10000000010016943412000031000103',
                                           data='1800000002001694341200003100010304000000e8030000')
        else:
            assert state['dispatcher_calls'] == [] and state['packets'] is None
        cases.append(state)

    # Preserve original VID records and command binding without repeating the
    # previous full command-map registration replay.
    m = base.machine()
    entries = []
    for i in range(10):
        a = 0x20201620+i*8
        kind, ptr = struct.unpack('<II',m.mem_read(a,8))
        if kind == 0xFF:
            break
        pairs = []
        for j in range(30):
            vid,pid = struct.unpack('<HH',m.mem_read(ptr+4*j,4))
            if not vid:
                break
            pairs.append(dict(vid=hex(vid),pid=hex(pid)))
        entries.append(dict(runtime_address=hex(a),kind=kind,pairs=pairs))
    binding = struct.unpack_from('<5I',raw,0x600309A4-0x60030000)
    assert binding == (0x407,0x4002F,0x60092EE1,0,0)
    report = dict(source=str(base.IMAGE),sha256=base.SHA,device_access=False,network_access=False,
        usb_capture=False,product_mapping_verified=False,synthetic_pid=True,
        classification=classifier,vid_table=entries,command_binding=dict(address='0x600309a4',words=list(binding)),
        cases=cases,executed_instructions=[executed[k] for k in sorted(executed)],
        fixtures=['Original VID classification/ops copy, then explicit task ops pointer fixture',
                  'Camera-ready byte fixture; no camera initialization/session/USB enumeration',
                  'One queue action 0x12/value1000 or queue failure; stop before second receive',
                  'Clock, locks, logger, OS semaphore substituted; transport stops before USB scheduler'],
        conclusion='Reference SIGMA selection returns 3 for numeric selector0x20 before any PTP call; Panasonic selection assembles9416/03010031. Task consumes but does not dispatch when ready=0 or ops=null.',
        limits=['Not a real Grip USB capture or verified physical firmware mapping',
                'No proof of the origin/unit/validity of numeric input or liveview/depth data',
                'Not all SIGMA control is unsupported; this result is limited to numeric selector0x20',
                'Changing VID alone does not implement a complete compatible camera handshake'])
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(classification=[dict(vid=x['vid'],kind=x['kind'],accepted=x['accepted']) for x in classifier],
                          cases=[dict(name=x['name'],dispatcher_returns=x['dispatcher_returns'],stop=x['stopped_at']) for x in cases],device_access=False)))


if __name__ == '__main__':
    main()
