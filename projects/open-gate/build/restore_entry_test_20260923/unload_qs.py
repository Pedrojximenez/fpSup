#!/usr/bin/env python3
"""Unload an already-built QS_CINE layout so the next Quick Set open re-parses
it through our ui_record hook.  Calls the firmware's own unload wrapper
FUN_c05d93a0(obj) (checks 'loaded' itself, takes the context lock inside
FUN_c05d91a0) from the shell task, via callfn.

Refuses unless QS_CINE is loaded and is not the current / next / held screen
(ctx+0x848/+0x84C/+0x850).  Keep Quick Set closed and hands off the camera.
"""
import signal, sys
sys.path.insert(0, '/Users/dido/Developer.localized/SIGMAfp_re/fpSup/fp_usb_shell')
signal.alarm(120)
from putfile import mem_get
from callfn import call

UNLOAD = 0xC05D93A0
QS_CINE_NAME = 0xC18DF064

ctx = mem_get(0xC37B7048, 1)[0]
vec = mem_get(ctx + 0x7C, 5)
ptrs = []
for i in range(0, vec[1], 16):
    ptrs += mem_get(vec[4] + 4 * i, min(16, vec[1] - i))
obj = next(p for p in ptrs if mem_get(p + 8, 1)[0] == QS_CINE_NAME)
tree = mem_get(obj + 0xC, 1)[0]
screens = mem_get(ctx + 0x848, 3)
print(f'ctx 0x{ctx:08X}  QS_CINE 0x{obj:08X}  tree 0x{tree:08X}  screens {[hex(s) for s in screens]}')
if not tree:
    sys.exit('QS_CINE is not loaded; nothing to do')
if obj in screens:
    sys.exit('QS_CINE is on screen; close Quick Set first')
ok, ret = call(UNLOAD, r0=obj)
print('unload returned', ret, '(0 = unloaded, 2 = was not loaded)')
print('tree after', hex(mem_get(obj + 0xC, 1)[0]), ' screens', [hex(s) for s in mem_get(ctx + 0x848, 3)])
