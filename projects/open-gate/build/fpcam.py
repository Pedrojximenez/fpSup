#!/usr/bin/env python3
"""相機測試框架 —— 強制「量真值、記基線、驗新檔、認版本」。

2026-09-15 建立。動機是同一天裡連續測錯五次,每次都是同一類原因:

  1. 拿代理指標當真值  —— `menu SetShutterSpeed` 讀的是快門速度模式的
     儲存值,與角度模式實際使用的曝光無關。用它量出來的東西全部無效。
  2. 沒驗證有沒有新 clip —— `rec log-out` 在錄影失敗時會回報**上一段**,
     於是「失敗」看起來像「成功但數字怪」。
  3. 沒有設定基線 —— 掃壞 `SetMovFramerate` 之後,把髒狀態造成的行為
     歸給了韌體版本。
  4. 沒確認 resident —— 對著不知道是哪一版的機器下結論。
  5. DNG 解析不嚴謹 —— 把所有 IFD 合成一個 dict,於是縮圖 IFD 的
     BitsPerSample=8 蓋掉了主影像的 12。

所以這裡的規則是硬的:

  * **唯一可信的量測是錄下來的 DNG。** 沒有別的捷徑。
  * 每次錄影都必須證明**產生了新的 clip**,否則算失敗。
  * 每個 session 開頭抓設定快照,結尾還原,中途所有改動都記錄。
  * 跑任何測試前先確認 resident 是哪一版。
  * DNG 逐 IFD 解析,主影像 = 面積最大的那個 IFD。
"""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SHELL = Path('/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
sys.path.insert(0, str(SHELL))
from putfile import sh as _sh  # noqa: E402

# 每個 session 都會快照/還原的設定。加東西進來是安全的;拿掉不安全。
WATCHED = (
    'SetMovRecSize', 'SetMovFramerate', 'SetMovCinemaDNGQuality',
    'SetMovRecFormat', 'SetMovQuality', 'SetMovBiningSupport',
    'SetCropMode', 'SetRecMode', 'SetShutterSpeed', 'SetShutterAngle',
    'SetShutterSpeedSettingMode',
)

TIFF_TYPESIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8, 11: 4, 12: 8}
TAGS = {
    254: 'NewSubfileType', 256: 'ImageWidth', 257: 'ImageLength',
    258: 'BitsPerSample', 259: 'Compression', 273: 'StripOffsets',
    279: 'StripByteCounts', 0x829A: 'ExposureTime', 34855: 'ISO',
    0xC61F: 'DefaultCropOrigin', 0xC620: 'DefaultCropSize',
    0xC61A: 'BlackLevel', 0xC61D: 'WhiteLevel', 0xC62A: 'BaselineExposure',
    0xC764: 'FrameRate',
}


class CameraError(RuntimeError):
    pass


def sh(cmd, **kw):
    try:
        return _sh(cmd, **kw).strip()
    except Exception as exc:                       # USB timeouts are routine
        raise CameraError(f'{cmd}: {exc}') from exc


def try_sh(cmd, **kw):
    try:
        return sh(cmd, **kw)
    except CameraError as exc:
        return f'ERR {exc}'


# ---------------------------------------------------------------- DNG 解析
def parse_dng(path):
    """逐 IFD 解析,回傳 (主影像 tags, 全部 IFD)。

    主影像 = ImageWidth x ImageLength 面積最大的 IFD。合併所有 IFD 是
    2026-09-15 的錯誤來源:縮圖 IFD 的 BitsPerSample=8 會蓋掉主影像的 12。
    """
    data = Path(path).read_bytes()
    if data[:2] not in (b'II', b'MM'):
        raise ValueError('不是 TIFF/DNG')
    bo = '<' if data[:2] == b'II' else '>'
    ifds = []

    def read_ifd(off, depth=0):
        if depth > 3 or not (0 < off < len(data) - 2):
            return
        count = struct.unpack_from(bo + 'H', data, off)[0]
        if count > 512:
            return
        tags = {}
        for i in range(count):
            ent = off + 2 + i * 12
            if ent + 12 > len(data):
                return
            tag, typ, cnt = struct.unpack_from(bo + 'HHI', data, ent)
            size = TIFF_TYPESIZE.get(typ, 1) * cnt
            voff = struct.unpack_from(bo + 'I', data, ent + 8)[0] if size > 4 else ent + 8
            if tag == 0x14A:                      # SubIFDs
                base = struct.unpack_from(bo + 'I', data, ent + 8)[0] if size > 4 else ent + 8
                for k in range(cnt):
                    if base + k * 4 + 4 <= len(data):
                        read_ifd(struct.unpack_from(bo + 'I', data, base + k * 4)[0], depth + 1)
                continue
            if tag == 0x8769:                     # EXIF
                read_ifd(struct.unpack_from(bo + 'I', data, ent + 8)[0], depth + 1)
                continue
            name = TAGS.get(tag)
            if not name or voff + size > len(data):
                continue
            try:
                if typ == 3:
                    vals = struct.unpack_from(bo + f'{cnt}H', data, voff)
                elif typ in (4, 9):
                    vals = struct.unpack_from(bo + f'{cnt}I', data, voff)
                elif typ in (5, 10):
                    raw = struct.unpack_from(
                        bo + f'{2 * cnt}' + ('i' if typ == 10 else 'I'), data, voff)
                    vals = tuple(f'{raw[2 * k]}/{raw[2 * k + 1]}' for k in range(cnt))
                elif typ == 1:
                    vals = struct.unpack_from(bo + f'{cnt}B', data, voff)
                else:
                    continue
            except struct.error:
                continue
            tags[name] = vals[0] if len(vals) == 1 else tuple(vals)
        ifds.append(tags)
        nxt = struct.unpack_from(bo + 'I', data, off + 2 + count * 12)[0]
        if nxt and depth == 0:
            read_ifd(nxt, depth + 1)

    read_ifd(struct.unpack_from(bo + 'I', data, 4)[0])
    sized = [t for t in ifds if t.get('ImageWidth') and t.get('ImageLength')]
    if not sized:
        raise ValueError('沒有帶尺寸的 IFD')
    main = max(sized, key=lambda t: t['ImageWidth'] * t['ImageLength'])
    return main, ifds


# ---------------------------------------------------------------- 相機
class Camera:
    def __init__(self, log=None):
        self.log_path = Path(log) if log else None
        self.events = []
        self.baseline = None
        sh('version')                              # 早點失敗

    # -- 記錄 -------------------------------------------------------
    def note(self, kind, **kw):
        self.events.append(dict(t=time.strftime('%H:%M:%S'), kind=kind, **kw))
        if self.log_path:
            self.log_path.write_text(json.dumps(self.events, ensure_ascii=False, indent=1))

    # -- 版本 -------------------------------------------------------
    def resident(self):
        """卡上 VSHL 的 sha256 前 16 碼 + 已知 build 的名字。"""
        tmp = tempfile.mktemp(suffix='.bin')
        subprocess.run([sys.executable, 'getfile.py', '\\VSHL.BIN', tmp,
                        '--size', '32768'], capture_output=True, cwd=SHELL)
        if not os.path.exists(tmp):
            return None, 'VSHL 取不到'
        import hashlib
        digest = hashlib.sha256(Path(tmp).read_bytes()).hexdigest()[:16]
        os.unlink(tmp)
        here = Path(__file__).resolve().parent
        for d in sorted(here.iterdir()):
            f = d / 'VSHL.BIN'
            if d.is_dir() and f.is_file():
                if hashlib.sha256(f.read_bytes()).hexdigest()[:16] == digest:
                    return digest, d.name
        return digest, '未知 build'

    # -- 設定 -------------------------------------------------------
    def snapshot(self):
        snap = {k: try_sh(f'menu {k}') for k in WATCHED}
        self.note('snapshot', settings=snap)
        if self.baseline is None:
            self.baseline = dict(snap)
        return snap

    def apply(self, **settings):
        """設定並讀回驗證。讀不回同一個值就是錯誤,不是警告。"""
        for key, want in settings.items():
            sh(f'menu Set{key} {want}')
            time.sleep(1.5)
            got = try_sh(f'menu Set{key}')
            if got != str(want):
                raise CameraError(f'Set{key} 設成 {want} 但讀回 {got}')
        self.note('apply', settings=settings)
        time.sleep(1.5)

    def restore(self):
        if not self.baseline:
            return
        for key, val in self.baseline.items():
            if val.startswith('ERR'):
                continue
            try:
                sh(f'menu {key} {val}')
                time.sleep(0.6)
            except CameraError:
                pass
        self.note('restore', settings=self.baseline)

    # -- 錄影 -------------------------------------------------------
    def clips(self):
        out = sh('dir \\CINEMA')
        return {m.group(1) for line in out.splitlines()
                if (m := re.search(r'(A\d{3}_\d{3})\s*$', line))}

    def record(self, seconds=2.0):
        """錄一段,**必須**產生新的 clip,否則丟例外。"""
        before = self.clips()
        for cmd in ('key MOVON', 'key MOVOFF'):
            try:
                _sh(cmd, retries=0)
            except Exception:
                pass
            time.sleep(0.15)
        time.sleep(seconds)
        for cmd in ('key MOVON', 'key MOVOFF'):
            try:
                _sh(cmd, retries=0)
            except Exception:
                pass
            time.sleep(0.15)
        time.sleep(3.0)
        for _ in range(6):
            if '-> 0' in try_sh('status get is_recording'):
                break
            time.sleep(1.0)
        new = sorted(self.clips() - before)
        if not new:
            self.note('record_failed')
            raise CameraError('錄影沒有產生新的 clip')
        self.note('record', clip=new[-1])
        return new[-1]

    def frame_tags(self, clip, index=1, nbytes=131072):
        """抓該 clip 第 index 幀的檔頭並解析。"""
        remote = f'\\CINEMA\\{clip}\\{clip}_{time.strftime("%Y%m%d")}_{index:06d}.DNG'
        tmp = tempfile.mktemp(suffix='.dng')
        subprocess.run([sys.executable, 'getfile.py', remote, tmp,
                        '--size', str(nbytes), '--partial'],
                       capture_output=True, cwd=SHELL)
        if not os.path.exists(tmp) or os.path.getsize(tmp) < 1024:
            raise CameraError(f'取不到 {remote}')
        try:
            main, _ = parse_dng(tmp)
        finally:
            os.unlink(tmp)
        self.note('frame', clip=clip, tags={k: str(v) for k, v in main.items()})
        return main


# ---------------------------------------------------------------- 測試
def check(tags, expect):
    """回傳 (通過?, 每一項的結果字串)。"""
    rows, ok = [], True
    for key, want in expect.items():
        got = tags.get(key)
        if isinstance(want, tuple):
            got_t = tuple(got) if isinstance(got, tuple) else (got,)
            good = got_t == want
        else:
            good = got == want
        ok &= good
        rows.append(f"    {key:<18} {str(got):<18} {'✔' if good else '✘ 預期 ' + str(want)}")
    return ok, rows


def run(cam, tests, seconds=2.0):
    digest, build = cam.resident()
    print(f'build: {build}  (VSHL {digest})')
    base = cam.snapshot()
    print('設定基線:', ' '.join(f'{k[3:]}={v}' for k, v in base.items()
                                if not v.startswith('ERR')))
    results = []
    try:
        for t in tests:
            print(f"\n── {t['name']}")
            try:
                cam.apply(**t['set'])
                clip = cam.record(t.get('seconds', seconds))
                tags = cam.frame_tags(clip)
            except CameraError as exc:
                print(f'    ✘ {exc}')
                results.append((t['name'], False))
                continue
            ok, rows = check(tags, t['expect'])
            print(f'    clip {clip}')
            print('\n'.join(rows))
            results.append((t['name'], ok))
    finally:
        cam.restore()
    print('\n' + '=' * 46)
    for name, ok in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    return all(ok for _, ok in results)
