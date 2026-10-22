"""shl.py — 透過 USB 轉發韌體自己的 shell 指令。

worker 早就支援 `shl <cmd>`,把整行交給韌體的指令執行器 FUN_c03d9c20,並用一個
捕捉 sink 收回主控台輸出。**77 條指令 + 子指令全部可用**。卡上那份 recsafe
AutoRun 就帶著 FN_SHEXEC / FN_SHPUSH / FN_SHINIT,這條路一直是通的。

為什麼重要:worker 自己的 `mem set` / `mem read` 是**刻意加了護欄**的
(原始碼註解:"Hardened: Bounded ranges cap blast radius"):

    WR_LO/WR_HI = 0xC072F060..0xC072F07C   寫入只准這 32 bytes
    RD_LO/RD_HI = 0xC0000000..0xC1000000   讀取只准這一段
    INJ_LO/INJ_HI = 0xC072F100..0xC0730000 注入區

我一整輪撞到的「寫入被靜默忽略」「0xC375xxxx 讀不到」「池寫不進去」「scratch 只剩
512 bytes」——全部是這些護欄,不是 USB shell 的天生缺陷。`shl mem set ...` 走的是
韌體自己的 mem,沒有這些界限。

用法:
    shl.run(sh, "mem set 0xC00D0794 0xEB197C19")
    shl.run(sh, "memmgr bufmem get 0 0x800000")

輸出捕捉緩衝只有 256 bytes(worker 的 CAP_SZ),長輸出會被截斷。
"""

def run(sh, command, timeout=12):
    """把 command 交給韌體 shell,回傳捕捉到的輸出(bytes)。

    自己開 socket 而不用 sh._round —— 後者等的是「含 payload 且 >=60 bytes」的回覆,
    遇到 ERR 短回覆會一路等到 65 秒逾時。曾經因此把一次正常的失敗誤判成相機當機。"""
    import socket
    with sh._lk:
        try:
            import telemetry as _t
            _t.wait_quiet()
        except Exception:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(timeout)
        try:
            s.connect(sh.sockpath)
            s.sendall(f"ECHO shl {command}\n".encode())
            buf = b""
            while b"\n" not in buf and len(buf) < 4096:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            return buf
        except socket.timeout:
            return b"TIMEOUT"
        finally:
            s.close()


def payload(sh, command):
    """只取回覆裡的 payload_hex,解成 bytes。"""
    raw = run(sh, command)
    text = raw.decode("latin1", "replace")
    marker = "payload_hex="
    i = text.find(marker)
    if i < 0:
        return b"", text.strip()
    hexpart = text[i + len(marker):].split()[0]
    try:
        return bytes.fromhex(hexpart), text.strip()
    except ValueError:
        return b"", text.strip()
