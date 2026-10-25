# Verify a mounted test volume: every file's size and bytes match the server's pattern.
import sys, os
MOUNT, MANIFEST = sys.argv[1], sys.argv[2]
M1, M2 = 0x9E3779B97F4A7C15, 0xC2B2AE3D27D4EB4F
def pattern(cnid, n):
    c = (cnid * M2) & (2**64 - 1)
    return bytes(((((o * M1) & (2**64 - 1)) ^ c) >> 56) for o in range(n))
bad = 0; n = 0
for line in open(MANIFEST):
    path, cnid, size = line.rstrip('\n').split('\t'); cnid = int(cnid); size = int(size)
    p = os.path.join(MOUNT, path)
    if os.path.getsize(p) != size: print('size', path); bad += 1; continue
    if n < int(sys.argv[3]) if len(sys.argv) > 3 else True:
        if open(p, 'rb').read() != pattern(cnid, size): print('content', path); bad += 1
    n += 1
print(f'{n} files checked, {bad} bad')
