#!/usr/bin/env python3
"""DFD 綠通道 AF-band 工作台 — live 1D 逐線綠 band 能量 profile。

每輪:呼叫注入的複製常式(把 AF 綠 band DMA buffer slot1 拷到 worker cave 0xC072FA00),
再一次 read_mem 拿回 256 個逐線值,連同 mposm / peakNow 一起服務。
瀏覽器 http://localhost:8771/ 畫 live profile 曲線 + 焦點/峰值。
用 MF 慢慢掃對焦看 profile 變化。慢 poll(避 AF-drive wedge)。
"""
import pathlib, sys, struct, threading, time, json
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / 'usb-shell-sup/fpshell_tool/monitor'))
import fpstate as F
from http.server import BaseHTTPRequestHandler, HTTPServer

CODE=0xC072F900; DST=0xC072FA00; N=256
MPOSM=0xC3291958; PEAKNOW=0xC32915C4; PEAKMAX=0xC32915C8
# afcopy: copy 256 words from *(0xC3404768) (AF green-band slot1 bufptr) to DST
AFCOPY=[0xe92d4010,0xe3040768,0xe34c0340,0xe5900000,0xe30f1a00,0xe34c1072,
        0xe3a02c01,0xe4903004,0xe4813004,0xe2522001,0x1afffffb,0xe8bd8010]

sh=F.Shell('/tmp/fpshell.sock', mock=False)
def si(a):
    import struct as S
    return S.unpack('<i', S.pack('<I', sh.peek32(a)))[0]

STATE={'mposm':0,'peak':0,'peakmax':0,'alive':False,'profile':[]}
LOCK=threading.Lock()

def setup():
    sh._ensure_peek()
    for i,x in enumerate(AFCOPY): sh._set_mem(CODE+i*4, x)

def poller():
    setup()
    while True:
        try:
            mp=si(MPOSM); pn=si(PEAKNOW); pmx=si(PEAKMAX)
            sh._call(CODE)                       # copy live green-band buffer -> DST
            raw=sh.read_mem(DST, N*4)
            prof=list(struct.unpack('<%di'%N, raw))
            with LOCK:
                STATE.update(mposm=mp,peak=pn,peakmax=pmx,alive=True,profile=prof)
        except Exception:
            with LOCK: STATE['alive']=False
        time.sleep(1.3)

PAGE = ("""<!doctype html><meta charset=utf-8><title>DFD Green Band</title>
<style>body{background:#0d0d0d;color:#ddd;font-family:ui-monospace,monospace;margin:16px}
h1{font-size:15px;color:#6f6}.v{font-size:20px;color:#fd6}.lab{color:#888;font-size:12px}
#s{color:#6f6}.dead{color:#f66}canvas{background:#151515;border:1px solid #333;margin-top:10px}</style>
<h1>DFD 綠通道 AF-band 工作台 — 逐線綠 band 能量 profile</h1>
<div><span class=lab>shell</span> <span id=s>?</span> &nbsp;
<span class=lab>mposm(對焦)</span> <span class=v id=mp>-</span> &nbsp;
<span class=lab>peakNow</span> <span class=v id=pn>-</span> &nbsp;
<span class=lab>peakMax</span> <span id=pmx>-</span> &nbsp;
<span class=lab>profile 總和</span> <span id=sum>-</span></div>
<div class=lab style=margin-top:6px>用 MF 慢慢掃對焦 — 合焦時高頻線條變利、profile 峰起伏加大</div>
<canvas id=c width=900 height=320></canvas>
<script>
async function tick(){try{let d=await(await fetch('/data.json')).json();
 S('s',d.alive?'alive':'busy');document.getElementById('s').className=d.alive?'':'dead';
 S('mp',d.mposm);S('pn',d.peak);S('pmx',d.peakmax);
 let sum=d.profile.reduce((a,b)=>a+Math.abs(b),0);S('sum',sum);draw(d.profile);}catch(e){}}
function S(id,v){document.getElementById(id).textContent=v;}
function draw(p){let c=document.getElementById('c'),g=c.getContext('2d');g.clearRect(0,0,c.width,c.height);
 if(!p||p.length<2)return;let mx=Math.max(...p.map(Math.abs))||1,W=c.width-20,H=c.height-30;
 g.strokeStyle='#6f6';g.lineWidth=1.4;g.beginPath();
 p.forEach((v,i)=>{let x=10+i/(p.length-1)*W,y=10+H-Math.abs(v)/mx*H;i?g.lineTo(x,y):g.moveTo(x,y);});g.stroke();
 g.fillStyle='#888';g.font='11px monospace';g.fillText('線 0 → '+(p.length-1)+'   峰='+mx,14,c.height-8);}
setInterval(tick,1000);tick();
</script>""").encode('utf-8')

class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        if self.path=='/data.json':
            with LOCK: body=json.dumps(STATE).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(PAGE))); self.end_headers(); self.wfile.write(PAGE)

if __name__=='__main__':
    threading.Thread(target=poller,daemon=True).start()
    print('DFD 綠通道工作台: http://localhost:8771/')
    HTTPServer(('127.0.0.1',8771),H).serve_forever()
