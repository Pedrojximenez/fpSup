"""telemetry.py — 儀表板的 hook-push 資料源,取代 host 輪詢。

舊做法:/state.json 每 30ms、/imu.json 每 20ms,每輪十幾筆 shell 交易 → 約 400 筆/秒,
把 USB 端點打到 LIBUSB_ERROR_IO / NO_DEVICE。

新做法(hook-push,見 memory prefer-hook-push):相機端 arm ctx4 TRB + StartTransfer,
host 只做 bulk-IN。**一個 BATCHPUSH 命令換回 N 筆記錄**,per-sample 零命令。
20 筆/次 ⇒ 每秒 2 次抓取就有 40 筆樣本,USB 命令量是舊做法的 1/200。

常式原始碼:camera/telemetry_push.S
"""
import socket, struct, os, threading, time

CODE   = 0xC072F600      # 與 daemon BATCHPUSH 寫死的 call 位址一致
RECORD = 0xC072F400      # CPU 視角;常式寫的是 uncached 別名 0x4072F400
MAGIC  = 0x31545046      # 'FPT1'
DUMP   = "/tmp/batchpush.bin"
ARG_DELAY = 0xC072F07C   # 每幀節流延遲(0 = 自由跑)

# V1 = 只有 IMU,已實機驗證(0.137ms/筆,連抓穩定)。這是預設。
TELEM_WORDS_V1 = (
    0xe92d4ff0,
    0xe1a04000,
    0xe5947070,
    0xe5946078,
    0xe59f80e0,
    0xe594a07c,
    0xe3a09000,
    0xe59f00e0,
    0xe5880000,
    0xe3a00001,
    0xe588001c,
    0xe5889004,
    0xe59f10c4,
    0xe1d120f0,
    0xe1d130f2,
    0xe1d100f4,
    0xe1c821b0,
    0xe1c831b2,
    0xe1c801b4,
    0xe59f10ac,
    0xe5911000,
    0xe5912060,
    0xe5923000,
    0xe5883018,
    0xe2433004,
    0xe1d300f0,
    0xe1d310f2,
    0xe1d320f6,
    0xe1c800b8,
    0xe1c810ba,
    0xe1c820bc,
    0xf57ff04f,
    0xe3030274,
    0xe34c031e,
    0xe5905000,
    0xe5858000,
    0xe3a00000,
    0xe5850004,
    0xe5856008,
    0xe3000813,
    0xe585000c,
    0xf57ff04f,
    0xe3a00009,
    0xe306cb81,
    0xe34cc01e,
    0xe12fff3c,
    0xe3a00004,
    0xe30c1350,
    0xe304ce81,
    0xe34cc01e,
    0xe12fff3c,
    0xe35a0000,
    0x0a000003,
    0xe1a0000a,
    0xe308c9c4,
    0xe34cc01f,
    0xe12fff3c,
    0xe2899001,
    0xe2577001,
    0x1affffce,
    0xe3a00000,
    0xe8bd8ff0,
    0x4072f400,
    0xc377790c,
    0xc31e3fcc,
    0x31545046,
)

# V2 = 再加 AF / 追蹤框 / 人臉 / 曝光。**尚未驗證**:第一次啟用就把 worker 弄掛
# (需拔電池)。要開之前必須先逐一 peek32 確認那 13 個位址安全,並且
# framesize 32→96 要單獨先驗一次 —— 上次兩件事一起改,分不出是哪個。
TELEM_WORDS_V2 = (
    0xe92d4ff0,
    0xe1a04000,
    0xe5947070,
    0xe5946078,
    0xe59f81cc,
    0xe3a09000,
    0xe59f01d0,
    0xe5880000,
    0xe3a00003,
    0xe588001c,
    0xe5889004,
    0xe59f11b4,
    0xe1d120f0,
    0xe1d130f2,
    0xe1d100f4,
    0xe1c821b0,
    0xe1c831b2,
    0xe1c801b4,
    0xe59f119c,
    0xe5911000,
    0xe5912060,
    0xe5923000,
    0xe5883018,
    0xe2433004,
    0xe1d300f0,
    0xe1d310f2,
    0xe1d320f6,
    0xe1c800b8,
    0xe1c810ba,
    0xe1c820bc,
    0xe30605a0,
    0xe34c0320,
    0xe5901000,
    0xe5881020,
    0xe30406a4,
    0xe34c0320,
    0xe5901000,
    0xe5881024,
    0xe30105b0,
    0xe34c0329,
    0xe5901000,
    0xe5881028,
    0xe30805e8,
    0xe34c0329,
    0xe5901000,
    0xe588102c,
    0xe30806b4,
    0xe34c0329,
    0xe5901000,
    0xe5881030,
    0xe30105c4,
    0xe34c0329,
    0xe5901000,
    0xe5881034,
    0xe30a06ac,
    0xe34c0343,
    0xe5901000,
    0xe588104c,
    0xe30a06b8,
    0xe34c0343,
    0xe5901000,
    0xe5881050,
    0xe30a06cc,
    0xe34c0343,
    0xe5901000,
    0xe5881054,
    0xe30a06d4,
    0xe34c0343,
    0xe5d01000,
    0xe5881058,
    0xe3030e00,
    0xe34c0303,
    0xe1d010f0,
    0xe1d020f2,
    0xe1d030f4,
    0xe1c813b8,
    0xe1c823ba,
    0xe1c833bc,
    0xe1d010f6,
    0xe1d022f6,
    0xe1c813be,
    0xe1c824b0,
    0xe30c0e6c,
    0xe34c037c,
    0xe5901000,
    0xe1c814b2,
    0xe30c0e7c,
    0xe34c037c,
    0xe1d010f0,
    0xe1d020f2,
    0xe1d030f4,
    0xe1c814b4,
    0xe1c824b6,
    0xe1c834b8,
    0xe1d010f6,
    0xe1c814ba,
    0xf57ff04f,
    0xe3030274,
    0xe34c031e,
    0xe5905000,
    0xe5858000,
    0xe3a00000,
    0xe5850004,
    0xe5856008,
    0xe3000813,
    0xe585000c,
    0xf57ff04f,
    0xe3a00009,
    0xe306cb81,
    0xe34cc01e,
    0xe12fff3c,
    0xe3a00004,
    0xe30c1350,
    0xe304ce81,
    0xe34cc01e,
    0xe12fff3c,
    0xe2899001,
    0xe2577001,
    0x1affff92,
    0xe3a00000,
    0xe8bd8ff0,
    0x4072f400,
    0xc377790c,
    0xc31e3fcc,
    0x31545046,
)

USE_V2 = False
TELEM_WORDS = TELEM_WORDS_V2 if USE_V2 else TELEM_WORDS_V1
FRAME = 0x60 if USE_V2 else 0x20   # V1 推 32B(IMU);V2 推 96B(全欄位)


def ensure(sh):
    """常式注入一次即可;重連或相機重開後要再叫一次。"""
    if getattr(sh, "_telem_ready", False):
        return
    with sh.lock():
        for i, x in enumerate(TELEM_WORDS):
            sh._set_mem(CODE + 4 * i, x)
    sh._telem_ready = True


# ---- 全域 BATCHPUSH 閘門 + 靜默期 ----
#
# 實測修正(重要):問題**不是**「兩個 BATCHPUSH 靠太近」,是
# 「BATCHPUSH 之後太快下任何命令」。證據:
#     成功  fetch → sleep(0.5) → ping → sleep(1.2) → fetch   ×5 全過
#     失敗  fetch → ping(立刻)                                → EP84 halt
# 第一個 BATCHPUSH 本身是成功的,是緊接著那個 ECHO 把端點打掛的。
# 所以靜默期要蓋住**所有**後續流量,而不只是下一個 BATCHPUSH ——
# 因此 Shell._round 也會呼叫 wait_quiet()。
# 實測:兩個 BATCHPUSH 靠太近會把 EP84 打成 LIBUSB_ERROR_PIPE(端點 halt),
# 重起 daemon 救不回來,要拔插 USB。一般 ECHO 命令密集下則完全沒事 —— 脆弱的只有這個。
# telemetry 與 lensdump 都必須走這裡,規則才有意義(各自守是守不住的)。
MIN_GAP  = 1.5    # 兩個 BATCHPUSH 之間
POST_GAP = 1.0    # BATCHPUSH 之後,任何命令之前
_BP_LOCK = threading.Lock()
# 時間戳寫在檔案裡,不是行程記憶體 —— 因為**靜默期必須跨行程**。
# 踩過:控制台行程剛跑完推送,另一個診斷腳本的 _BP_LAST 是 0,直接放行 → halt。
# 任何會下命令的工具都會經過這裡,所以共用一個檔案就守得住。
_BP_STAMP = "/tmp/fpshell_lastpush"


def _stamp_read():
    try:
        return os.path.getmtime(_BP_STAMP)
    except OSError:
        return 0.0


def _stamp_write():
    try:
        with open(_BP_STAMP, "w") as f:
            f.write("1")
    except OSError:
        pass


def health(sockpath="/tmp/fpshell.sock", timeout=10, sh=None):
    """檢查 shell 是否還活著 —— **一定要用這個**,不要自己開裸 socket 送 ECHO。

    直接用裸 socket 在 BATCHPUSH 之後立刻 ping,會繞過靜默期並把 EP84 打掛
    (今天被自己的測試腳本坑過兩次)。這裡先等靜默期。
    """
    if sh is not None:            # 有串流在跑時,這裡會擋到它放手
        sh.lock().acquire()
    try:
        wait_quiet()
        return _ping(sockpath, timeout)
    finally:
        if sh is not None:
            sh.lock().release()


def _ping(sockpath, timeout):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sockpath)
        s.sendall(b"ECHO echo p\n")
        return b"OK" in s.recv(90)
    except Exception:
        return False
    finally:
        s.close()


def wait_quiet():
    """BATCHPUSH 之後的靜默期。Shell._round 每次送命令前都會呼叫(跨行程有效)。"""
    w = POST_GAP - (time.time() - _stamp_read())
    if w > 0:
        time.sleep(w)


def batchpush(sockpath, framesize, nframes, timeout=120):
    with _BP_LOCK:
        wait = MIN_GAP - (time.time() - _stamp_read())
        if wait > 0:
            time.sleep(wait)
        _stamp_write()                      # 推送期間也算「忙」,別的行程會等
        try:
            return _bp_send(sockpath, framesize, nframes, timeout)
        finally:
            _stamp_write()


def _bp_send(sockpath, framesize, nframes, timeout):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(sockpath)
        s.sendall(f"BATCHPUSH {framesize} {nframes}\n".encode())
        buf = b""
        while b"\n" not in buf:
            c = s.recv(512)
            if not c:
                break
            buf += c
        return buf.decode(errors="replace").strip()
    finally:
        s.close()


def parse(blob):
    """把 bulk-IN 回來的位元組流拆成記錄。"""
    out = []
    for o in range(0, len(blob) - FRAME + 1, FRAME):
        magic, seq = struct.unpack_from("<II", blob, o)
        if magic != MAGIC:
            continue
        gx, gy, gz = struct.unpack_from("<hhh", blob, o + 0x08)
        ax, ay, az = struct.unpack_from("<hhh", blob, o + 0x10)
        cur, flags = struct.unpack_from("<II", blob, o + 0x18)
        rec = {"seq": seq, "cursor": cur, "flags": flags,
               "gyro": {"x": gx / 131.0, "y": gy / 131.0, "z": gz / 131.0,
                        "raw": [gx, gy, gz]},
               "accel": {"x": ax / 1024.0, "y": ay / 1024.0, "z": az / 1024.0,
                         "raw": [ax, ay, az]}}
        if flags & 2 and len(blob) - o >= 0x60:
            drive, area, route, chi, clo, peak = struct.unpack_from("<IIIIII", blob, o + 0x20)
            bx, by, bw, bh, bconf, fmode = struct.unpack_from("<hhhhhh", blob, o + 0x38)
            fx, fy, fw, fh = struct.unpack_from("<hhhh", blob, o + 0x44)
            gain, iso, again, hcg = struct.unpack_from("<IIII", blob, o + 0x4C)
            rec["af"] = {"drive": drive, "area": area, "route": route,
                         "contrast_hi": chi, "contrast_lo": clo, "peak_now": peak,
                         "state": "searching" if drive in (4, 8) else "idle"}
            rec["aat"] = {"x": bx, "y": by, "w": bw, "h": bh, "confidence": bconf}
            rec["faces"] = ([{"x": fx, "y": fy, "w": fw, "h": fh}]
                            if (fmode and fw > 0) else [])
            rec["face_mode"] = fmode
            rec["exposure"] = {"gain_state": gain, "iso": iso,
                               "analog_gain": again / 65536.0, "hcg": bool(hcg)}
        out.append(rec)
    return out


def fetch(sh, sockpath, nframes=20):
    """抓一批遙測。回傳 (records, info)。

    gyro 是 2500Hz 而推送速率由 host bulk-IN 決定,所以同一筆樣本可能被推很多次;
    用記錄裡的 ring cursor 去重,只留真正的新樣本。
    """
    ensure(sh)
    with sh.lock():
        resp = batchpush(sockpath, FRAME, nframes, timeout=30)
        blob = b""
        if os.path.exists(DUMP):
            with open(DUMP, "rb") as f:
                blob = f.read()
    recs = parse(blob)
    fresh, last = [], None
    for r in recs:
        if r["cursor"] != last:
            fresh.append(r)
            last = r["cursor"]
    return fresh, {"pushed": len(recs), "unique": len(fresh), "daemon": resp}


# ---------- 連續串流(一個命令,邊推邊讀) ----------
#
# 為什麼不是「一次抓 N 筆」:那種做法要等整批收完才寫檔,所以看到的永遠是過去的資料,
# N 越大反而越不即時。改成 daemon 每收一幀就 fflush,這裡邊推邊讀 → 延遲降到一幀。
# 而且整段只有**一個** BATCHPUSH,那 1 秒靜默期在串流中途不會被觸發。
MAX_FRAMES = 1000000        # daemon 的 nframes 上限(已放寬;原本 20000)
# 一段串流的長度。分段的代價是每段之間有 1 秒靜默期(約 5% duty),
# 換來的是「要停的時候最多只等這麼久」——串流全程持鎖,期間誰都下不了命令。
# 不節流(delay=0)實測約 9000 fps → 這麼多幀 ≈ 44 秒/段。
# 段與段之間的接縫會凍約 1.5 秒(靜默期),所以段越長接縫越少;
# 代價是要停止串流最多得等一段跑完,所以不要無限拉長。
#
# 為什麼可以不節流了:節流本來的唯一理由是 daemon 的 20000 幀上限
# (不節流兩三秒就燒完額度,被迫一直重下命令、一直付靜默期)。上限放寬後,
# 不節流反而更好 —— 拿到完整 2500Hz 取樣,接縫也一樣罕見。
# (陀螺儀本身 2500Hz,超過的部分是重複讀同一個環形位置,靠 cursor 去重。)
CHUNK_FRAMES = 400000

class Stream:
    """背景跑一個長 BATCHPUSH,持續把最新一筆記錄放進 self.last。"""

    def __init__(self, sh, sockpath, delay=0, hz_guess=2500):
        self.sh, self.sockpath, self.delay = sh, sockpath, delay
        self.last = None
        self.count = 0
        self.rate = 0.0
        self.err = None
        self._stop = threading.Event()
        self._delay_set = False
        self._th = None
        self.hz_guess = hz_guess

    def start(self):
        if self._th and self._th.is_alive():
            return
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            try:
                ensure(self.sh)
                # ★ 整段推送都持鎖:推送**進行中**下任何命令一樣會把 EP84 打掛
                #   (不只是推送之後)。持鎖讓其他人根本拿不到通道,而不是靠自律。
                with self.sh.lock():
                    if not self._delay_set:
                        # 節流值不會變,設一次就好。放在每段開頭的話,那個命令本身
                        # 要先等 1 秒靜默期,等於把接縫拉長一倍。
                        self.sh._set_mem(ARG_DELAY, self.delay)
                        self._delay_set = True
                    # 先砍掉舊檔:daemon 雖然會 truncate,但 _tail 可能搶在 truncate 之前
                    # 讀到上一輪的殘留,把游標推過頭 → 之後永遠追不上新資料(踩過)。
                    try:
                        os.remove(DUMP)
                    except OSError:
                        pass
                    rd = threading.Thread(target=self._tail, daemon=True)
                    rd.start()
                    batchpush(self.sockpath, FRAME, CHUNK_FRAMES, timeout=600)
                    self._reading = False
                    rd.join(timeout=2)
            except Exception as e:
                self.err = f"{type(e).__name__}: {e}"
                self._reading = False
                time.sleep(2)

    def _tail(self):
        """邊推邊讀:檔案長多少就吃多少,永遠拿最新的一筆。"""
        self._reading = True
        pos, t0, n0 = 0, time.time(), self.count
        # 等檔案被 daemon 重新建立
        deadline = time.time() + 10
        while time.time() < deadline and not os.path.exists(DUMP):
            time.sleep(0.02)
        while self._reading and not self._stop.is_set():
            try:
                sz = os.path.getsize(DUMP)
            except OSError:
                time.sleep(0.05); continue
            if sz >= pos + FRAME:
                whole = ((sz - pos) // FRAME) * FRAME
                with open(DUMP, "rb") as f:
                    f.seek(pos)
                    blob = f.read(whole)
                pos += whole
                recs = parse(blob)
                if recs:
                    self.last = recs[-1]
                    self.count += len(recs)
                dt = time.time() - t0
                if dt >= 1.0:
                    self.rate = (self.count - n0) / dt
                    t0, n0 = time.time(), self.count
            else:
                time.sleep(0.01)
