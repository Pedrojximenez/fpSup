#!/usr/bin/env python3
"""DFD 工作台 — live Bayer-green sharpness (peakNow) vs focus (mposm) curve.

背景執行緒慢 poll shell(mposm 0xC3291958 + peakNow 0xC32915C4),累積 {mposm: peakNow} 點;
HTTP 服務一個頁面在 http://localhost:8771/ 畫 live 焦點-銳度曲線。
用法:MF 手動慢慢掃對焦 → 曲線在瀏覽器累積成形。慢 poll(避開 AF-drive wedge)。
"""
import socket, struct, threading, time, json
from http.server import BaseHTTPRequestHandler, HTTPServer

SOCK='/tmp/fpshell.sock'; PC=0xC072F100; PA=0xC072F064; PR=0xC072F068
MPOSM=0xC3291958; PEAKNOW=0xC32915C4; PEAKMAX=0xC32915C8

def rnd(l,to=2.0):
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(to)
    try:
        s.connect(SOCK); s.sendall(l.encode()); b=b''
        while len(b)<1024:
            c=s.recv(1024)
            if not c: break
            b+=c
            if b'payload' in b: break
        return b
    finally: s.close()
def rd(a,n=4):
    r=rnd(f"ECHO mem read 0x{a:08X} {n}\n"); j=r.find(b'payload_hex=')
    if j>=0: return bytes.fromhex(r[j+12:].split(b'\n',1)[0].decode())[:n]
    raise IOError('bad')
def peek(a):
    rnd(f"ECHO mem set 0x{PA:08X} 0x{a:08X}\n"); rnd(f"ECHO call 0x{PC:08X}\n")
    return struct.unpack('<i', rd(PR,4))[0]

STATE={'mposm':0,'peak':0,'peakmax':0,'alive':False,'n':0}
PTS={}          # mposm -> peakNow (latest)
LOCK=threading.Lock()

def poller():
    while True:
        try:
            mp=peek(MPOSM); pn=peek(PEAKNOW); pmx=peek(PEAKMAX)
            with LOCK:
                STATE.update(mposm=mp,peak=pn,peakmax=pmx,alive=True)
                PTS[mp]=pn; STATE['n']=len(PTS)
        except Exception:
            with LOCK: STATE['alive']=False
        time.sleep(1.2)

PAGE=b"""<!doctype html><meta charset=utf-8><title>DFD Workbench</title>
<style>body{background:#111;color:#ddd;font-family:ui-monospace,monospace;margin:16px}
h1{font-size:16px;color:#6cf} .v{font-size:22px;color:#fd6} .lab{color:#888;font-size:12px}
#s{color:#6f6} .dead{color:#f66} canvas{background:#181818;border:1px solid #333;margin-top:10px}
button{background:#333;color:#ddd;border:1px solid #555;padding:6px 12px;cursor:pointer;margin-right:8px}</style>
<h1>DFD 工作台 — Bayer-綠銳度(peakNow) vs 對焦(mposm)</h1>
<div><span class=lab>shell</span> <span id=s>?</span> &nbsp;
<span class=lab>mposm</span> <span class=v id=mp>-</span> &nbsp;
<span class=lab>peakNow</span> <span class=v id=pn>-</span> &nbsp;
<span class=lab>peakMax</span> <span id=pmx>-</span> &nbsp;
<span class=lab>點數</span> <span id=n>0</span></div>
<div style=margin-top:8px><button onclick=clr()>清空曲線</button>
<span class=lab>用 MF 慢慢掃對焦,曲線會累積成形(合焦=峰,失焦=谷)</span></div>
<canvas id=c width=760 height=340></canvas>
<script>
let cur=null;
async function tick(){
 try{let r=await fetch('/data.json');let d=await r.json();
  document.getElementById('s').textContent=d.alive?'alive':'busy';
  document.getElementById('s').className=d.alive?'':'dead';
  document.getElementById('mp').textContent=d.mposm;
  document.getElementById('pn').textContent=d.peak;
  document.getElementById('pmx').textContent=d.peakmax;
  document.getElementById('n').textContent=d.n;
  draw(d.pts);
 }catch(e){}
}
function draw(pts){
 let c=document.getElementById('c'),g=c.getContext('2d');
 g.clearRect(0,0,c.width,c.height);
 let xs=Object.keys(pts).map(Number).sort((a,b)=>a-b);
 if(xs.length<2)return;
 let ys=xs.map(x=>pts[x]);
 let xmin=Math.min(...xs),xmax=Math.max(...xs),ymax=Math.max(...ys)||1;
 let W=c.width-60,H=c.height-40,X=x=>50+(x-xmin)/(xmax-xmin+1e-9)*W,Y=y=>10+H-y/ymax*H;
 g.strokeStyle='#333';g.beginPath();g.moveTo(50,10);g.lineTo(50,10+H);g.lineTo(50+W,10+H);g.stroke();
 g.strokeStyle='#6cf';g.lineWidth=2;g.beginPath();
 xs.forEach((x,i)=>{let px=X(x),py=Y(pts[x]);i?g.lineTo(px,py):g.moveTo(px,py);});g.stroke();
 g.fillStyle='#fd6';xs.forEach(x=>{g.beginPath();g.arc(X(x),Y(pts[x]),2.5,0,7);g.fill();});
 g.fillStyle='#888';g.font='11px monospace';
 g.fillText('mposm '+xmin+' → '+xmax,55,10+H+16);
 g.save();g.translate(14,180);g.rotate(-Math.PI/2);g.fillText('peakNow(銳度) 0→'+ymax,0,0);g.restore();
}
async function clr(){await fetch('/clear');}
setInterval(tick,1000);tick();
</script>"""

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path=='/data.json':
            with LOCK:
                d=dict(STATE); d['pts']=dict(PTS)
            body=json.dumps(d).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        elif self.path=='/clear':
            with LOCK: PTS.clear(); STATE['n']=0
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
        else:
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE)

if __name__=='__main__':
    threading.Thread(target=poller,daemon=True).start()
    print('DFD 工作台: http://localhost:8771/')
    HTTPServer(('127.0.0.1',8771),H).serve_forever()
