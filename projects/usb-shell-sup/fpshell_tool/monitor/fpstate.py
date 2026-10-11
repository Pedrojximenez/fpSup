#!/usr/bin/env python3
"""fpstate.py — SIGMA fp 萬能監控台 (all-purpose monitor) host reader + web server.

Reads live camera state over the USB shell's `mem read` and serves dashboard.html
+ /state.json. Each item is a pointer-chase + interpretation using the RE'd
addresses (notes/CAMERA_STATE_SOURCES.md, notes/AF_LIVE_STATE_MAP.md,
SIGMA_FP_INTERNAL_GYRO_ARCHIVE). Run with --mock to develop the UI without a camera;
the real backend needs the daemon to return mem-read payloads as HEX (Codex host item).

Usage:
  ./fpstate.py --mock                 # synthetic data, open http://localhost:8770/
  ./fpstate.py --socket /tmp/fpshell.sock   # real (needs hex-capable daemon)
"""
import argparse, http.server, json, math, os, socket, struct, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------- addresses (from RE notes) ----------
A_GYRO_MBOX   = 0xC31E3FCC   # -> P (0x2E006004); ring_base = *(P+0x60); samples 8B {i16 X,Y,pad,Z}, /131 dps
A_ACCEL       = 0xC377790C   # MMA8452Q level cache: i16 X,Y,Z axis-remapped; g = raw/1024, ~100Hz
# ---- IMU one-call snapshot blob (camera/imu_snapshot.S) injected into the worker cave ----
# gathers accel XYZ + gyro-latest into RESULT in ONE `call`; host drains in ONE read (2 transactions).
# gyro latest sample = *(rb) - 4 ; rb = *(*(0xC31E3FCC)+0x60) ; scale /131 (=*(P+0x68)) dps, /1024 g.
SNAP_CODE, SNAP_RESULT = 0xC072F200, 0xC072F300
SNAP_WORDS = (
    0xE92D00F0, 0xE59F2058, 0xE59F1058, 0xE1D130F0, 0xE1D140F2, 0xE1D150F4, 0xE1C230B0,
    0xE1C240B2, 0xE1C250B4, 0xE59F1040, 0xE5911000, 0xE5916060, 0xE5967000, 0xE5827008,
    0xE2473004, 0xE1D340F0, 0xE1D350F2, 0xE1D300F6, 0xE1C240BC, 0xE1C250BE, 0xE1C201B0,
    0xE59F3014, 0xE5823014, 0xE8BD00F0, 0xE12FFF1E, 0xC072F300, 0xC377790C, 0xC31E3FCC,
    0x494D5530,
)
A_GAIN_G      = 0xC343A6A0   # +0x0c gain_state, +0x18 ISO/rel, +0x2c analog gain, +0x34 HCG byte
A_AF_DRIVE    = 0xC32065A0   # 4/8 = AF-C servo
A_AF_AREA     = 0xC32046A4   # 0 single /1 MF /3 tracking /5 global
A_AF_ROUTE    = 0xC32915B0
A_AF_CON_HI   = 0xC32985E8
A_AF_CON_LO   = 0xC32986B4
A_AF_PEAK_NOW = 0xC32915C4
A_AF_BODYMOT  = 0xC3404678   # +0x04 body-motion flag
A_DRIFT       = 0xC33D1958
A_AAT_BOX     = 0xC3033E00   # {i16 x,y,w,h}; conf @0xC3033E26
A_FACES       = 0xC37CCA9C   # 5 groups, stride 0x9C, rect@+0x3E0, mode@+0x3D0; 320x213 space
A_WORKER      = 0xC072F000   # our shell state ([0x5C]=cmds, [0x58]=faults)

# ---------- shell backend ----------
class Shell:
    def __init__(self, sockpath, mock=False):
        self.sockpath, self.mock = sockpath, mock
        self._t0 = time.time()
        # 多步驟序列(設參數→call→讀結果)必須不可分割,否則兩個執行緒會互相蓋掉
        # STATE 的暫存欄位(PEEK_ARG/PEEK_RES、鏡頭常式的 ARG0/ARG1)。
        self._lk = threading.RLock()

    def lock(self):
        return self._lk
    MAXCHUNK = 44   # FPSH payload cap; larger reads are chunked
    def read_mem(self, addr, n):
        if self.mock:
            return self._mock(addr, n)
        out = bytearray()
        off = 0
        while off < n:
            c = min(self.MAXCHUNK, n - off)
            out += self._read1(addr + off, c)
            off += c
        return bytes(out)
    def _read1(self, addr, n):
        # one shell mem-read (<=44 bytes). The daemon's "payload=" is followed by the RAW payload
        # bytes (%.*s byte-copy). We take exactly n bytes after it (binary-safe, no hex needed).
        raw = self._round(f"ECHO mem read 0x{addr:08X} {n}\n")
        j = raw.find(b"payload_hex=")
        if j >= 0:
            return bytes.fromhex(raw[j+12:].split(b"\n",1)[0].decode())[:n]
        i = raw.find(b"payload=")
        if i < 0:
            raise IOError(f"unexpected: {raw[:80]!r}")
        return raw[i+8 : i+8+n]
    # ---- generic peek (deref ANY address via the deployed worker; no read-table entry needed) ----
    # inject-once routine @0xC072F100: ldr r1,[r0,#0x64]; ldr r2,[r1]; str r2,[r0,#0x68]; bx lr
    PEEK_CODE = 0xC072F100
    PEEK_ARG  = 0xC072F064   # STATE+0x64 (scratch): address to deref
    PEEK_RES  = 0xC072F068   # STATE+0x68 (scratch): 32-bit result
    PEEK_WORDS = (0xE5901064, 0xE5912000, 0xE5802068, 0xE12FFF1E)
    def _set_mem(self, addr, val):
        self._round(f"ECHO mem set 0x{addr:08X} 0x{val & 0xFFFFFFFF:08X}\n")
    def _call(self, addr):
        self._round(f"ECHO call 0x{addr:08X}\n")
    def _ensure_peek(self):
        if getattr(self, "_peek_ready", False): return
        for i, w in enumerate(self.PEEK_WORDS):
            self._set_mem(self.PEEK_CODE + 4*i, w)
        self._peek_ready = True
    def peek32(self, addr):
        if self.mock:
            return struct.unpack('<I', self._mock(addr, 4))[0]
        with self._lk:
            self._ensure_peek()
            self._set_mem(self.PEEK_ARG, addr)
            self._call(self.PEEK_CODE)
            return struct.unpack('<I', self.read_mem(self.PEEK_RES, 4))[0]
    # ---- one-call IMU snapshot: accel XYZ + gyro-latest in 2 transactions ----
    def _ensure_snap(self):
        if getattr(self, "_snap_ready", False): return
        for i, w in enumerate(SNAP_WORDS):
            self._set_mem(SNAP_CODE + 4*i, w)
        self._snap_ready = True
    def imu(self):
        if self.mock:
            t = time.time() - self._t0
            gx,gy,gz = 200*math.sin(t*1.7), 150*math.sin(t*1.1+1), 90*math.sin(t*0.7+2)
            ax,ay,az = 120*math.sin(t*0.5), 90*math.cos(t*0.4), 1024
            return {"accel":{"x":ax/1024,"y":ay/1024,"z":az/1024},
                    "gyro":{"x":gx/131,"y":gy/131,"z":gz/131}, "cursor":0}
        self._ensure_snap()
        self._call(SNAP_CODE)
        raw = self.read_mem(SNAP_RESULT, 0x18)
        if struct.unpack_from('<I', raw, 0x14)[0] != 0x494D5530:
            raise IOError("IMU snapshot magic mismatch")
        ax,ay,az = struct.unpack_from('<hhh', raw, 0)
        cur = struct.unpack_from('<I', raw, 8)[0]
        gx,gy,gz = struct.unpack_from('<hhh', raw, 0x0C)
        return {"accel":{"x":ax/1024.0,"y":ay/1024.0,"z":az/1024.0},
                "gyro":{"x":gx/131.0,"y":gy/131.0,"z":gz/131.0}, "cursor":cur}
    def _round(self, line):
      with self._lk:
        try:                       # BATCHPUSH 之後的靜默期 —— 在最底層強制,誰都繞不過
            import telemetry as _t
            _t.wait_quiet()
        except Exception:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.settimeout(65)
        try:
            s.connect(self.sockpath); s.sendall(line.encode())
            buf = b""
            while len(buf) < 4096:
                chunk = s.recv(4096)
                if not chunk: break
                buf += chunk
                if b"\n" in buf and b"payload" in buf and len(buf) >= 60: break
            return buf
        finally:
            s.close()
    def _mock(self, addr, n):
        t = time.time() - self._t0
        b = bytearray(n)
        if addr == A_GYRO_MBOX: struct.pack_into('<I', b, 0, 0x2E006004)
        elif addr == 0x2E006004+0x60: struct.pack_into('<I', b, 0, 0x2E00644C)
        elif addr == 0x2E00644C: struct.pack_into('<I', b, 0, 8)           # head
        elif addr == 0x2E00644C+4: struct.pack_into('<hhhh', b, 0,
                int(2000*math.sin(t*1.7)), int(1500*math.sin(t*1.1+1)), int(900*math.sin(t*0.7+2)), 0)
        elif addr == A_ACCEL:                                   # peek word0: X,Y
            struct.pack_into('<hh', b, 0, int(120*math.sin(t*0.5)), int(90*math.cos(t*0.4)))
        elif addr == A_ACCEL+4:                                 # peek word1: Z
            struct.pack_into('<h', b, 0, 1024)
        elif addr == A_GAIN_G:
            struct.pack_into('<I', b, 0x0c, 3); struct.pack_into('<I', b, 0x18, 640)
            struct.pack_into('<I', b, 0x2c, 0x00010000); b[0x34] = 1
        elif addr == A_AF_DRIVE: struct.pack_into('<I', b, 0, 8 if int(t)%6<3 else 4)
        elif addr == A_AF_AREA: struct.pack_into('<I', b, 0, 3)
        elif addr == A_AF_ROUTE: struct.pack_into('<I', b, 0, int(t)%3)
        elif addr in (A_AF_CON_HI, A_AF_PEAK_NOW): struct.pack_into('<I', b, 0, int(1200+400*math.sin(t*2)))
        elif addr == A_AAT_BOX:
            struct.pack_into('<hhhh', b, 0, int(120+40*math.sin(t)), int(90+20*math.cos(t)), 70, 70)
            if n>0x26: struct.pack_into('<h', b, 0x26, 82)
        elif addr == A_FACES+0x3D0: struct.pack_into('<I', b, 0, 1)   # face mode on
        elif addr == A_FACES+0x3E0:
            struct.pack_into('<hhhh', b, 0, int(60+30*math.sin(t*0.6)), 70, 64, 64)
        elif addr == A_WORKER:
            struct.pack_into('<I', b, 0x5c, int(t*3)); struct.pack_into('<I', b, 0x58, 0)
        return bytes(b)

def u32(sh,a): return struct.unpack('<I', sh.read_mem(a,4))[0]

# 採集開關 —— host 輪詢已全面停用,只留 hook-push。其餘群組待改成 hook-push 後再開。
# 採集狀態跟著 telemetry 的版本走:V1 只有 IMU,V2 才含 AF/框/曝光(尚未驗證)。
def _collect():
    on = "hook-push" if telemetry.USE_V2 else False
    return {"imu": "hook-push", "af": on, "aat": on,
            "faces": on, "exposure": on, "shell": False}

# 最近一筆 hook-push 記錄 —— /state.json 直接用它,不再自己去讀相機。
# 一次 fetch 同時餵 /imu.json 與 /state.json,USB 命令量不變。
LAST = {"rec": None, "ts": 0.0}

def _level(a):
    roll  = math.degrees(math.atan2(a["x"], math.hypot(a["y"], a["z"])))
    pitch = math.degrees(math.atan2(a["y"], math.hypot(a["x"], a["z"])))
    return {**a, "roll": roll, "pitch": pitch,
            "mag": math.sqrt(a["x"]**2 + a["y"]**2 + a["z"]**2)}

STREAM = [None]

def get_stream(sh, sockpath):
    if STREAM[0] is None:
        STREAM[0] = telemetry.Stream(sh, sockpath, delay=0)   # 不節流,約 4566fps
        STREAM[0].start()
    return STREAM[0]


def imu_state(sh, sockpath, n=100):
    """IMU via hook-push:一個 BATCHPUSH 命令換回 n 筆記錄(舊做法是每筆一輪交易)。

    ⚠️ 節奏很重要:實測**密集連下 BATCHPUSH 會把端點弄死**(要拔電池)。
    穩定跑過的樣子是「間隔約 1 秒、一次抓一批」;250ms 連打則出過事。
    所以寧可**少次、每次多筆** —— 命令數更少,樣本數反而更多。

    回傳最新一筆維持前端原本的形狀,另外附 samples 讓曲線圖拿到整批。"""
    # 連續串流:相機一直在推,這裡只是把「當下最新那一筆」拿出來 —— 零 USB 成本。
    st = get_stream(sh, sockpath)
    last = st.last
    if not last:
        return {"ts": time.time(), "imu_err": st.err or "串流啟動中…",
                "info": {"fps": 0, "count": st.count}}
    info = {"fps": round(st.rate, 1), "count": st.count, "mode": "stream"}
    LAST["rec"], LAST["ts"] = last, time.time()
    return {"ts": time.time(), "source": "hook-push",
            "gyro": last["gyro"], "accel": _level(last["accel"]),
            "info": info}

# ---------- pollers ----------
def poll(sh):
    """全部改用 hook-push:直接吃最近一筆推送記錄,自己完全不碰相機。

    舊版每輪十幾筆 shell 交易、以 30ms 節奏跑 = 約 400 筆/秒,實測把 USB 端點打到
    LIBUSB_ERROR_IO → NO_DEVICE。現在 AF / 追蹤框 / 人臉 / 曝光都由 camera/telemetry_push.S
    在同一趟 gather 裡填進記錄,這裡零 USB 成本。"""
    st = {"source": "hook-push", "ts": time.time(), "collect": _collect()}
    r = LAST["rec"]
    if not r:
        st["note"] = "還沒收到推送記錄(等第一次 /imu.json)"
        return st
    st["age"] = round(time.time() - LAST["ts"], 3)
    for k in ("af", "aat", "faces", "exposure"):
        if k in r:
            st[k] = r[k]
    return st

# ---------- 鏡頭全資料下載 ----------
import lensdump, telemetry

SOCKPATH = ["/tmp/fpshell.sock"]
LENS = {"running": False, "done": 0, "total": 0, "label": "", "result": None, "error": None}

def _lens_worker(sh):
    def prog(done, total, label):
        LENS.update(done=done, total=total, label=label)
    try:
        LENS["result"] = lensdump.dump(sh, sockpath=SOCKPATH[0], progress=prog)
    except Exception as e:
        LENS["error"] = f"{type(e).__name__}: {e}"
    finally:
        LENS["running"] = False

def lens_start(sh):
    if LENS["running"]:
        return {"ok": False, "msg": "已經在跑了"}
    # running 必須在這裡就設好 —— 前端會在 start 回應後立刻輪詢,
    # 若等執行緒自己設,那一瞬間會讀到 running=False + 上一輪的 result,誤判成「已完成」而停止輪詢。
    LENS.update(running=True, done=0, total=0, label="準備中…", result=None, error=None)
    threading.Thread(target=_lens_worker, args=(sh,), daemon=True).start()
    return {"ok": True}

def lens_status():
    r = LENS.get("result")
    return {"running": LENS["running"], "done": LENS["done"], "total": LENS["total"],
            "label": LENS["label"], "error": LENS["error"],
            "ready": r is not None,
            "lens_name": (r or {}).get("lens_name"),
            "summary": (r or {}).get("summary")}

# ---------- server ----------
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def _json(self, obj):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200); self.send_header("Content-Type","application/json")
        self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def _blob(self, data, ctype, filename):
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path.startswith("/stream/stop"):
            # 停止串流的正確方式。硬殺行程會讓相機繼續推、沒人收 → 端點 wedge。
            st = STREAM[0]
            if not st: self._json({"ok": True, "msg": "沒有串流在跑"}); return
            st.stop()
            th = getattr(st, "_th", None)
            if th: th.join(timeout=90)
            STREAM[0] = None
            self._json({"ok": True, "msg": "串流已停止", "count": st.count}); return
        elif self.path.startswith("/lens/start"):
            self._json(lens_start(self.server.shell)); return
        elif self.path.startswith("/lens/status"):
            self._json(lens_status()); return
        elif self.path.startswith("/lens/data.json"):
            r = LENS.get("result")
            if not r: self._json({"error": "還沒有資料,先執行下載"}); return
            self._blob(json.dumps(r, indent=1, ensure_ascii=False).encode(),
                       "application/json", "lens_dump.json"); return
        elif self.path.startswith("/lens/data.txt"):
            r = LENS.get("result")
            if not r: self._blob(b"still nothing", "text/plain", "lens_dump.txt"); return
            self._blob(lensdump.to_text(r).encode(), "text/plain; charset=utf-8", "lens_dump.txt"); return
        elif self.path.startswith("/imu.json"):
            if LENS["running"]: self._json({"paused":"lens dump"}); return
            try: data = json.dumps(imu_state(self.server.shell, self.server.sockpath)).encode()
            except Exception as e: data = json.dumps({"imu_err":str(e)}).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        elif self.path.startswith("/state.json"):
            if LENS["running"]: self._json({"paused":"lens dump"}); return
            data = json.dumps(poll(self.server.shell)).encode()
            self.send_response(200); self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data))); self.end_headers(); self.wfile.write(data)
        else:
            try: body=open(os.path.join(HERE,"dashboard.html"),"rb").read()
            except OSError: body=b"dashboard.html missing"
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8")
            self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)

def _shutdown(*_a):
    """串流中被硬殺 = 相機還在推、host 卻沒人收 → 端點 wedge,要拔插 USB(踩過)。
    所以收到訊號時先讓當前分段跑完再退出。⚠️ 不要用 kill -9。"""
    st = STREAM[0]
    if st:
        print("停止串流,等當前分段跑完(最多約 45 秒)…", flush=True)
        st.stop()
        th = getattr(st, "_th", None)
        if th:
            th.join(timeout=90)
    os._exit(0)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--socket", default=os.environ.get("FPSHELL_SOCKET","/tmp/fpshell.sock"))
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--port", type=int, default=8770)
    args=ap.parse_args()
    import signal
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    srv=http.server.ThreadingHTTPServer(("127.0.0.1",args.port), Handler)
    srv.shell=Shell(args.socket, mock=args.mock)
    srv.sockpath=args.socket
    SOCKPATH[0]=args.socket
    print(f"SIGMA fp 萬能監控台 → http://localhost:{args.port}/   ({'MOCK' if args.mock else 'live '+args.socket})")
    srv.serve_forever()

if __name__=="__main__":
    main()
