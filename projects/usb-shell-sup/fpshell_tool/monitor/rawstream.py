#!/usr/bin/env python3
"""rawstream.py — live web viewer for the SIGMA fp liveview Bayer buffer.

Grabs the live LV raw buffer over the USB shell (RAWGRAB, capped <=4MB), decodes it,
and serves rendered frames to a browser page that auto-refreshes. You can switch
render mode (raw sensor vs firmware-style render) and tune width/format live from the UI.

Decode (empirically cracked 2026-08-19): the LV buffer at 0x49C00000 reads cleanly as
16-bit big-endian, width 1620 (oversampled FHD Bayer). raw_addr scan-confirmed live.
Firmware getter FUN_c031e6b0 documents a 12-bit MSB-first variant; 16BE/1620 is what
renders clean here — both selectable below so we can lock it against the real scene.

Run:  ./rawstream.py            then open http://localhost:8771/
"""
import argparse, http.server, io, socket, struct, urllib.parse
import numpy as np

DEF_ADDR = 0x49C00000
GRAB_BYTES = 0x380000          # 3.5MB (<=4MB worker cap); 1620*1080*2 = 3.5MB = one FHD frame

def grab(sockpath, addr, n):
    s = socket.socket(socket.AF_UNIX); s.settimeout(40); s.connect(sockpath)
    s.sendall(f"RAWGRAB {addr:x} {n}\n".encode()); r = s.recv(300).decode().strip(); s.close()
    if 'OK' not in r or 'rc=0' not in r:
        raise IOError(r)
    return np.fromfile('/tmp/rawgrab.bin', dtype=np.uint8)

def decode(b, width, fmt):
    if fmt == '16be':
        px = np.frombuffer(b.tobytes(), dtype='>u2').astype(np.float32)
    elif fmt == '16le':
        px = np.frombuffer(b.tobytes(), dtype='<u2').astype(np.float32)
    else:  # 12-bit firmware MSB-first (width interpreted as 2160-class)
        w = np.frombuffer(b.tobytes(), dtype='<u4')
        wpr = width*3//8; H = len(w)//wpr; w = w[:H*wpr].reshape(H, wpr)
        img = np.zeros((H, width), np.uint16)
        for x in range(8):
            cols = np.arange(0, width, 8); base = (cols//8)*3
            w0, w1, w2 = w[:, base], w[:, base+1], w[:, base+2]
            v = [w0 >> 20, (w0 >> 8) & 0xFFF, ((w0 & 0xFF) << 4) | (w1 >> 28),
                 (w1 >> 16) & 0xFFF, (w1 >> 4) & 0xFFF, ((w1 & 0xF) << 8) | (w2 >> 24),
                 (w2 >> 12) & 0xFFF, w2 & 0xFFF][x]
            img[:, cols+x] = v
        return img.astype(np.float32)
    H = px.size // width
    return px[:H*width].reshape(H, width)

def valid_crop(img):
    # drop trailing rows that are near-uniform (padding / next buffer)
    rv = img.var(1)
    good = np.where(rv > rv.max()*0.02)[0]
    return img[:good.max()+1] if len(good) else img

def stretch(x, p_lo, p_hi, gamma):
    lo, hi = np.percentile(x, [p_lo, p_hi])
    return np.clip((x - lo)/(hi - lo + 1e-6), 0, 1) ** (1/gamma)

def render(img, mode, phase='RGGB', wb=(1.6, 1.0, 1.5)):
    img = valid_crop(img)
    if mode == 'raw':
        g = stretch(img, 1, 99, 2.2)
        return (g*255).astype(np.uint8)                      # grayscale mosaic
    # demosaic by 2x2 super-pixel
    H, W = img.shape; h2, w2 = H//2*2, W//2*2
    q00 = img[0:h2:2, 0:w2:2]; q01 = img[0:h2:2, 1:w2:2]
    q10 = img[1:h2:2, 0:w2:2]; q11 = img[1:h2:2, 1:w2:2]
    R, G, B = q00, (q01+q10)/2, q11
    if mode == 'render':
        R = R*wb[0]; G = G*wb[1]; B = B*wb[2]               # simple WB toward neutral
    rgb = np.stack([stretch(R,1,99,2.2), stretch(G,1,99,2.2), stretch(B,1,99,2.2)], -1)
    return (rgb*255).astype(np.uint8)

def to_jpeg(arr):
    from PIL import Image
    im = Image.fromarray(arr)
    im.thumbnail((1280, 1280))
    buf = io.BytesIO(); im.save(buf, 'JPEG', quality=82); return buf.getvalue()

PAGE = ("""<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">
<title>fp Live Raw</title><style>
body{margin:0;background:#0b0d10;color:#e6edf3;font-family:ui-monospace,Menlo,monospace}
header{display:flex;gap:12px;align-items:center;padding:8px 14px;background:#14181d;border-bottom:1px solid #262d36;flex-wrap:wrap}
button,select,input{background:#1b2027;color:#e6edf3;border:1px solid #2f3742;border-radius:6px;padding:5px 10px;font:inherit;cursor:pointer}
button.on{background:#4cc2ff;color:#04121c;border-color:#4cc2ff}
#img{display:block;max-width:100%;margin:0 auto}
#stat{margin-left:auto;color:#8b98a5;font-size:12px}
label{color:#8b98a5;font-size:12px}
</style></head><body>
<header>
 <b>SIGMA fp Live Raw</b>
 <button id="m_raw" onclick="setMode('raw')">RAW sensor</button>
 <button id="m_render" class="on" onclick="setMode('render')">Render (sRGB)</button>
 <label>fmt <select id="fmt" onchange="refresh()"><option value="16be">16-bit BE</option><option value="16le">16-bit LE</option><option value="12">12-bit fw</option></select></label>
 <label>width <input id="w" type="number" value="1620" style="width:80px" onchange="refresh()"></label>
 <label><input id="live" type="checkbox" checked> live</label>
 <span id="stat">—</span>
</header>
<img id="img" src="">
<script>
let mode='render';
function setMode(m){mode=m;document.getElementById('m_raw').className=m=='raw'?'on':'';
 document.getElementById('m_render').className=m=='render'?'on':'';refresh();}
function url(){const f=document.getElementById('fmt').value,w=document.getElementById('w').value;
 return `/frame?mode=${mode}&fmt=${f}&width=${w}&t=`+Date.now();}
function refresh(){const im=document.getElementById('img');const t0=performance.now();
 const u=url();im.onload=()=>{document.getElementById('stat').textContent=
  `${Math.round(performance.now()-t0)}ms · ${mode} · ${document.getElementById('fmt').value} · w=${document.getElementById('w').value}`;
  if(document.getElementById('live').checked) setTimeout(refresh,50);};
 im.onerror=()=>{document.getElementById('stat').textContent='grab error (worker busy?)';setTimeout(refresh,600);};
 im.src=u;}
refresh();
</script></body></html>""").encode('utf-8')

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith('/frame'):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            mode = q.get('mode', ['render'])[0]; fmt = q.get('fmt', ['16be'])[0]
            width = int(q.get('width', ['1620'])[0])
            try:
                b = grab(self.server.sockpath, self.server.addr, GRAB_BYTES)
                img = decode(b, width, fmt)
                jpg = to_jpeg(render(img, mode))
                self.send_response(200); self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', str(len(jpg))); self.end_headers(); self.wfile.write(jpg)
            except Exception as e:
                self.send_response(503); self.send_header('Content-Type', 'text/plain')
                msg = str(e).encode(); self.send_header('Content-Length', str(len(msg))); self.end_headers(); self.wfile.write(msg)
        else:
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--socket', default='/tmp/fpshell.sock')
    ap.add_argument('--addr', type=lambda x: int(x, 0), default=DEF_ADDR)
    ap.add_argument('--port', type=int, default=1025)
    args = ap.parse_args()
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), H)
    srv.sockpath = args.socket; srv.addr = args.addr
    print(f"fp live raw viewer -> http://localhost:{args.port}/   (buffer 0x{args.addr:08X})")
    srv.serve_forever()

if __name__ == '__main__':
    main()
