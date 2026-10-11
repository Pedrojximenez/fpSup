#!/usr/bin/env python3
"""lens_probe.py — read L-mount lens memory over the USB shell.
CmdRead(ctx, addr, len, dest, 0) @0xC0355BE0 via an injected routine.
ctx: 0xC347CB14 (runtime, low registers) or 0xC347D098 (mount ctx, big optical blocks).
"""
import pathlib, sys, socket
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'usb-shell-sup/fpshell_tool/monitor'))
import fpstate as F
LENS_WORDS = (0xE92D4FF0,0xE59F402C,0xE5940000,0xE5941004,0xE5942008,0xE59F3020,0xE3A05000,
              0xE52D5004,0xE59FC018,0xE12FFF3C,0xE28DD004,0xE584000C,0xE8BD4FF0,0xE12FFF1E,
              0xC072FF00,0xC072FA00,0xC0355BE0)
CODE, SCR, DEST = 0xC072F980, 0xC072FF00, 0xC072FA00
CTX_RUNTIME, CTX_MOUNT = 0xC347CB14, 0xC347D098
class LensProbe:
    def __init__(self, sock='/tmp/fpshell.sock'):
        self.sh=F.Shell(sock,mock=False); self._inj=False
    def _inject(self):
        if self._inj: return
        for i,w in enumerate(LENS_WORDS): self.sh._set_mem(CODE+4*i,w)
        self._inj=True
    def read(self, addr, n, ctx=CTX_RUNTIME, timeout=8):
        self._inject()
        self.sh._set_mem(SCR+0, ctx); self.sh._set_mem(SCR+4, addr&0xFFFFFF); self.sh._set_mem(SCR+8, n&0xFF)
        s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(timeout)
        try: s.connect('/tmp/fpshell.sock'); s.sendall(f'ECHO call 0x{CODE:08X}\n'.encode()); s.recv(128)
        except Exception: s.close(); return None, None
        s.close()
        ret=F.u32(self.sh, SCR+12); data=self.sh.read_mem(DEST, min(n,0xFF))
        return ret, data
    def read_block(self, addr, total, ctx=CTX_MOUNT):
        out=bytearray()
        for off in range(0, total, 0xF0):
            ret,d=self.read(addr+off, min(0xF0,total-off), ctx)
            if d is None: return None, out
            out+=d
        return 'ok', out
