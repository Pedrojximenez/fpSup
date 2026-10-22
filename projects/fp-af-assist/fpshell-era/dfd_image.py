#!/usr/bin/env python3
"""DFD live 影像工作台 — 綠通道 live 影像 via hook-push。

背景執行緒配速:BATCHPUSH 一整幀 YUYV 顯示 buffer(push_disp @0xC072F600 讀 latch 0xC375BF88)→
抽綠通道 → PNG;瀏覽器 http://localhost:8771/ 看即時綠通道影像 + 亮度。
需先注入 push_disp。11-15fps(每幀 4MB @311MB/s + 解碼)。
"""
import sys, socket, threading, time, io
import numpy as np
from PIL import Image
from http.server import BaseHTTPRequestHandler, HTTPServer

W, H = 1920, 1088
FRAME = W * H * 2
LATEST = {'green': None, 'luma': None, 'ts': 0, 'n': 0}
LOCK = threading.Lock()

def daemon_cmd(line, to=20):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(to)
    try:
        s.connect('/tmp/fpshell.sock'); s.sendall((line+'\n').encode()); b = b''
        while len(b) < 512:
            c = s.recv(512)
            if not c: break
            b += c
            if b'\n' in b: break
        return b.decode(errors='replace')
    finally: s.close()

def decode(d):
    a = np.frombuffer(d[:FRAME], dtype=np.uint8).reshape(H, W, 2)
    # YUYV: byte0=Y (luma, has structure), byte1=U/V (chroma ~128)
    Y = a[:, :, 0].astype(np.float32); C = a[:, :, 1].astype(np.float32)
    U = np.repeat(C[:, 0::2], 2, axis=1)[:, :W]
    V = np.repeat(C[:, 1::2], 2, axis=1)[:, :W]
    G = np.clip(Y - 0.344*(U-128) - 0.714*(V-128), 0, 255).astype(np.uint8)
    rgb = np.zeros((H, W, 3), dtype=np.uint8); rgb[:, :, 1] = G
    def png(arr, mode):
        buf = io.BytesIO(); Image.fromarray(arr).save(buf, 'PNG'); return buf.getvalue()
    return png(rgb, 'RGB'), png(Y.astype(np.uint8), 'L')

def poller():
    n = 0
    while True:
        try:
            r = daemon_cmd(f"BATCHPUSH {FRAME} 1")
            if 'OK frames=1/1' in r:
                with open('/tmp/batchpush.bin', 'rb') as f: d = f.read(FRAME)
                if len(d) >= FRAME:
                    g, l = decode(d); n += 1
                    with LOCK: LATEST.update(green=g, luma=l, ts=time.time(), n=n)
        except Exception:
            pass
        time.sleep(0.15)

PAGE = ("""<!doctype html><meta charset=utf-8><title>DFD Green Live</title>
<style>body{background:#0a0a0a;color:#ccc;font-family:ui-monospace,monospace;margin:10px;text-align:center}
h1{font-size:14px;color:#6f6}img{max-width:98vw;border:1px solid #333;margin-top:6px}
.tab{margin:6px}button{background:#333;color:#ccc;border:1px solid #555;padding:5px 12px;cursor:pointer}</style>
<h1>DFD 綠通道 Live 影像 (hook-push, 311MB/s)</h1>
<div class=tab><button onclick="ch='green'">綠通道</button> <button onclick="ch='luma'">亮度</button>
<span id=n></span></div>
<img id=im>
<script>let ch='luma';
setInterval(()=>{document.getElementById('im').src='/'+ch+'.png?'+Date.now();
 fetch('/n').then(r=>r.text()).then(t=>document.getElementById('n').textContent='frame #'+t);},200);
</script>""").encode('utf-8')

class Hd(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith('/green.png'):
            with LOCK: b = LATEST['green']
            self._img(b)
        elif self.path.startswith('/luma.png'):
            with LOCK: b = LATEST['luma']
            self._img(b)
        elif self.path == '/n':
            with LOCK: n = LATEST['n']
            body = str(n).encode(); self.send_response(200)
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(200); self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE)
    def _img(self, b):
        if not b: self.send_response(503); self.end_headers(); return
        self.send_response(200); self.send_header('Content-Type', 'image/png')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

if __name__ == '__main__':
    threading.Thread(target=poller, daemon=True).start()
    print('DFD 綠通道 Live 影像: http://localhost:8771/')
    HTTPServer(('127.0.0.1', 8771), Hd).serve_forever()
