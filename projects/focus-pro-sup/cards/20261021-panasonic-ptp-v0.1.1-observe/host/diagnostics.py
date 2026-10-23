#!/usr/bin/env python3
"""Read the existing FPCP v1 diagnostic ring; import/decode never opens USB.

No arguments prints help. --usb explicitly uses PyUSB/libusb. Only standard
DeviceInfo/session operations and the prototype's read-only 95F0 are sent.
No reset, configuration change, driver detach, motion, retries or shell calls.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

MAGIC, HEADER, RECORDS, RECORD_SIZE = 0x50435046, 64, 48, 24
SNAPSHOT_SIZE = HEADER + RECORDS * RECORD_SIZE
COUNTERS = ('magic', 'version', 'requests', 'submitted', 'rejected', 'replayed',
            'io_failed', 'poisoned', 'identity_calls', 'last_tid', 'last_target',
            'last_response', 'extended_session', 'next_record', 'capacity', 'record_bytes')
RESPONSES = {0x2001: 'OK', 0x2002: 'GeneralError', 0x2003: 'SessionNotOpen',
             0x2004: 'InvalidTransactionID', 0x2005: 'OperationNotSupported',
             0x2007: 'IncompleteTransfer', 0x200f: 'AccessDenied/NotPossible',
             0x2019: 'DeviceBusy', 0x201d: 'InvalidParameter', 0x201e: 'SessionAlreadyOpen'}


class ProtocolError(ValueError):
    pass


def packet(kind, code, tid, body=b''):
    return struct.pack('<IHHI', 12 + len(body), kind, code, tid) + body


def decode(raw):
    """Accept a 1,216-byte payload or its exact 95F0 PTP data container."""
    if raw[:4] != b'FPCP':
        if len(raw) < 12:
            raise ProtocolError('Short diagnostic data')
        size, kind, op, _ = struct.unpack_from('<IHHI', raw)
        if size != len(raw) or kind != 2 or op != 0x95f0:
            raise ProtocolError('Expected FPCP payload or 95F0 data container')
        raw = raw[12:]
    if len(raw) != SNAPSHOT_SIZE:
        raise ProtocolError(f'Expected {SNAPSHOT_SIZE} diagnostic bytes, got {len(raw)}')
    h = dict(zip(COUNTERS, struct.unpack_from('<16I', raw)))
    if (h['magic'], h['capacity'], h['record_bytes']) != (MAGIC, RECORDS, RECORD_SIZE) or h['version'] not in (1, 2):
        raise ProtocolError('Unsupported diagnostic format')
    h['last_target'] = struct.unpack_from('<i', raw, 40)[0]
    rows = []
    for slot in range(RECORDS):
        values = struct.unpack_from('<6I', raw, HEADER + slot * RECORD_SIZE)
        if values[0] == 0:
            if any(values):
                raise ProtocolError('Nonempty uncommitted ring slot')
            continue
        row = dict(zip(('sequence', 'transaction', 'opcode', 'parameter', 'response', 'detail'), values))
        if (values[0] - 1) % RECORDS != slot or values[2] > 0xffff or values[4] > 0xffff:
            raise ProtocolError('Invalid ring record')
        row['response_name'] = RESPONSES.get(row['response'], 'Unknown')
        if h['version'] == 2 and row['response'] == 0x2005:
            if row['opcode'] == 0x9416 and row['parameter'] == 0x03010031:
                row['numeric_value_u32'] = row['detail']
                row['numeric_units'] = 'unconfirmed'
            elif row['opcode'] == 0x940b and row['parameter'] == 0x0800001b:
                if row['detail'] > 0xffff:
                    raise ProtocolError('Invalid observed 16-bit setting')
                row['setting_u16'] = row['detail']
        rows.append(row)
    rows.sort(key=lambda x: x['sequence'])
    expected = list(range(max(1, h['next_record'] - RECORDS + 1), h['next_record'] + 1))
    if [r['sequence'] for r in rows] != expected:
        raise ProtocolError('Incomplete/inconsistent diagnostic ring (sequence wrap unsupported)')
    observations = []
    if h['identity_calls']:
        observations.append('USB 身分 hook 曾執行；不表示 DJI 已完成相機握手。')
    if h['submitted']:
        observations.append('曾有原生鏡頭提交被接受；此為累計值，不表示鏡頭完成移動或合焦。')
    else:
        observations.append('此實例尚無被接受的原生鏡頭提交。')
    if any(r['opcode'] == 0x9416 and r['parameter'] == 0x03010031 and r['response'] == 0x2005 for r in rows):
        observations.append('保留紀錄包含被拒絕的 03010031 數值對焦命令；尺度仍未確定。')
    if any(r['opcode'] in (0x9411, 0x9412) and r['response'] == 0x2005 for r in rows):
        observations.append('保留紀錄包含被相容層拒絕的 SIGMA 原廠雲台對焦命令。')
    if any(r['opcode'] == 0x9416 and r['parameter'] == 0x03010011 and r['response'] == 0x2019 for r in rows):
        observations.append('相對對焦曾被 busy／拍攝／event／位置重查等守衛拒絕；現格式無法區分各守衛。')
    if h['poisoned']:
        observations.append('此實例已因資料階段錯誤停用動作；需另核對 USB 封包。')
    return {'format': f'FPCP v{h["version"]}', 'payload_sha256': hashlib.sha256(raw).hexdigest(),
            'header': h, 'records': rows, 'observations': observations,
            'limits': ['僅保留最近 48 筆相容層紀錄；原廠 pass-through 命令不在此環中。',
                       '缺少某命令不表示它從未發生，初始化可能已被輪詢覆蓋。',
                       '原型沒有記錄 data payload 全文或實體鏡頭完成事件。']}


def device_identity(data):
    """Bounded standard PTP DeviceInfo decoder; refuse other camera profiles."""
    pos = 0

    def take(n):
        nonlocal pos
        if n < 0 or pos + n > len(data):
            raise ProtocolError('Truncated DeviceInfo')
        b = data[pos:pos + n]
        pos += n
        return b

    def string():
        n = take(1)[0]
        if n == 0:
            return ''
        b = take(n * 2)
        if b[-2:] != b'\0\0':
            raise ProtocolError('Unterminated PTP string')
        return b[:-2].decode('utf-16le', errors='strict')

    standard, vendor, extension = struct.unpack('<HIH', take(8))
    description = string()
    take(2)
    for _ in range(5):
        n, = struct.unpack('<I', take(4))
        if n > 4096:
            raise ProtocolError('DeviceInfo array too large')
        take(n * 2)
    manufacturer, model, version, serial = [string() for _ in range(4)]
    if pos != len(data):
        raise ProtocolError('Unexpected DeviceInfo tail')
    return {'standard': standard, 'vendor_extension': vendor, 'extension_version': extension,
            'extension_description': description, 'manufacturer': manufacturer,
            'model': model, 'version': version, 'serial': serial}


class Link:
    """One exclusive USB bulk stream, bounded reads and no uncertain retries."""
    def __init__(self, dev, ep_out, ep_in, timeout_ms=2000):
        self.dev, self.ep_out, self.ep_in = dev, ep_out, ep_in
        self.timeout_ms, self.buffer, self.clean = timeout_ms, bytearray(), True

    def _read(self, deadline):
        for _ in range(64):
            if len(self.buffer) >= 4:
                n, = struct.unpack_from('<I', self.buffer)
                if n < 12 or n > 8192:
                    raise ProtocolError('Invalid PTP container length')
                if len(self.buffer) >= n:
                    result = bytes(self.buffer[:n])
                    del self.buffer[:n]
                    return result
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ProtocolError('PTP deadline expired; request was not retried')
            chunk = self.dev.read(self.ep_in, 4096, timeout=max(1, int(remaining * 1000)))
            self.buffer.extend(chunk)
            if len(self.buffer) > 16384:
                raise ProtocolError('PTP stream exceeded bound')
        raise ProtocolError('Too many PTP fragments')

    def exchange(self, op, tid, *params):
        if op not in (0x1001, 0x1002, 0x1003, 0x95f0):
            raise ProtocolError('Operation is outside the diagnostic allowlist')
        if (op == 0x1002 and (len(params) != 1 or not params[0])) or (op != 0x1002 and params):
            raise ProtocolError('Invalid diagnostic request parameters')
        if not self.clean or self.buffer:
            raise ProtocolError('Stream state is uncertain; no further request sent')
        self.clean = False
        deadline = time.monotonic() + self.timeout_ms / 1000
        out = packet(1, op, tid, struct.pack('<' + 'I' * len(params), *params))
        if self.dev.write(self.ep_out, out, timeout=self.timeout_ms) != len(out):
            raise ProtocolError('Short USB write; request was not retried')
        payload = None
        for _ in range(2):
            incoming = self._read(deadline)
            size, kind, code, got_tid = struct.unpack_from('<IHHI', incoming)
            if got_tid != tid:
                raise ProtocolError('Unexpected transaction; no drain/reset/retry performed')
            if kind == 2 and code == op and payload is None:
                payload = incoming[12:]
                continue
            if kind != 3 or size > 32 or (size - 12) % 4:
                raise ProtocolError('Unexpected PTP response')
            if self.buffer:
                raise ProtocolError('Unexpected data after PTP response')
            self.clean = True
            return code, payload
        raise ProtocolError('Missing terminal PTP response')


def collect(link):
    rc, data = link.exchange(0x1001, 0)
    if rc != 0x2001 or data is None:
        raise ProtocolError('DeviceInfo failed')
    identity = device_identity(data)
    if (identity['vendor_extension'], identity['manufacturer'], identity['model']) != (
            0x1c, 'SIGMA', 'fp Focus PTP prototype'):
        raise ProtocolError('This is not the FPCP prototype; 95F0 was not sent')
    rc, _ = link.exchange(0x1002, 0, 0x46504350)
    if rc not in (0x2001, 0x201e):
        raise ProtocolError(f'OpenSession returned {rc:04X}')
    owned = rc == 0x2001
    audit = {'identity': identity, 'session': 'opened_by_reader' if owned else 'existing_not_closed'}
    try:
        rc, data = link.exchange(0x95f0, 1)
        if rc != 0x2001 or data is None:
            raise ProtocolError(f'95F0 failed ({rc:04X})')
        report = decode(data)
    except Exception:
        if owned and link.clean:
            try:
                link.exchange(0x1003, 2)
            except Exception:
                pass
        raise
    if owned:
        try:
            close_rc, _ = link.exchange(0x1003, 2)
            audit['close_response'] = f'{close_rc:04X}'
        except Exception as e:
            audit['close_error'] = str(e)  # keep the completed capture even if close fails
    report['reader'] = audit
    return data, report


def read_usb():
    try:
        import usb.core
        import usb.util
    except ImportError as e:
        raise ProtocolError('--usb requires PyUSB and a libusb backend; offline decode needs neither') from e
    devices = list(usb.core.find(find_all=True, idVendor=0x04da, idProduct=0x2382))
    if len(devices) != 1:
        raise ProtocolError(f'Expected one prototype USB device 04DA:2382, found {len(devices)}')
    dev = devices[0]
    claimed = False
    try:
        cfg = dev.get_active_configuration()
        choices = []
        for intf in cfg:
            if (intf.bInterfaceClass, intf.bInterfaceSubClass, intf.bInterfaceProtocol,
                    intf.bAlternateSetting) != (6, 1, 1, 0):
                continue
            eps = [e for e in intf if usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK]
            inputs = [e for e in eps if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN]
            outputs = [e for e in eps if usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT]
            if len(inputs) == len(outputs) == 1:
                choices.append((intf, outputs[0], inputs[0]))
        if len(choices) != 1:
            raise ProtocolError('Expected one active PTP interface with a bulk IN/OUT pair')
        intf, ep_out, ep_in = choices[0]
        usb.util.claim_interface(dev, intf.bInterfaceNumber)
        claimed = True
        return collect(Link(dev, ep_out.bEndpointAddress, ep_in.bEndpointAddress))
    finally:
        try:
            if claimed:
                usb.util.release_interface(dev, intf.bInterfaceNumber)
        finally:
            usb.util.dispose_resources(dev)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    modes = ap.add_mutually_exclusive_group()
    modes.add_argument('--decode', type=Path, help='decode an existing FPCP payload/container offline')
    modes.add_argument('--usb', action='store_true', help='explicitly query the connected prototype')
    ap.add_argument('--out', type=Path, help='new local output directory (required for --usb)')
    args = ap.parse_args(argv)
    if not args.usb and not args.decode:
        ap.print_help()
        return 0
    if args.usb and args.out is None:
        ap.error('--usb requires --out NEW_DIRECTORY')
    if args.out:
        args.out.mkdir(parents=True, exist_ok=False)
    try:
        if args.usb:
            raw, report = read_usb()
        else:
            raw = args.decode.read_bytes()
            report = decode(raw)
        if args.out:
            (args.out / 'snapshot.bin').write_bytes(raw)
            (args.out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except Exception as e:
        print(f'Diagnostic read failed: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
