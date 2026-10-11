#!/usr/bin/env python3
"""用 HDMI 擷取量 live view 的閃爍。輸出是數字,不是「看起來有沒有閃」。

    python3 lvflicker.py 30 "原廠電池 + USB 拔掉"

三個必要的旗標(2026-09-27 各踩一次):
  -framerate N 放在 -i 之前   avfoundation 回報假時基 1000k tbr
  -fps_mode passthrough       否則 ffmpeg 瘋狂複製幀(曾寫出 202 GB)
  -frames:v N 而非 -t         計數,免疫於假時間戳;-fs 當硬上限

兩個必須先擋掉的假訊號:
  1. 擷取卡的第一幀是殘幕(只填部分畫面)。不丟掉開頭 3 幀,它一個人就
     製造 556 mEV 的假峰對峰,把真訊號(3 mEV)完全蓋掉。
  2. **沒有訊號時擷取卡送的是它自己的 "No Signal" 靜止卡** —— 逐幀差
     恆為 0,偵測器會報「0 事件」,看起來像「閃爍消失了」。assert_live()
     擋這個:活的相機畫面光是雜訊就有 ~1.7 位階的逐幀差。

偶發閃爍要用**事件偵測(6σ + MAD)**,不是變異數,而且窗要 20 秒以上 ——
每 6-10 秒一次的事件,2 秒的窗量不到,p2p/std 也會把它稀釋掉。
"""
import os, subprocess, sys, numpy as np

W, H = 1920, 1080
SKIP = 3                      # 擷取卡的殘幕


def grab(path, seconds, dev="0", fps=30):
    if os.path.exists(path):
        os.unlink(path)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-f", "avfoundation", "-framerate", str(fps),
                    "-pixel_format", "uyvy422", "-i", dev,
                    "-fps_mode", "passthrough",
                    "-frames:v", str(int(seconds * fps)),
                    "-pix_fmt", "gray", "-fs", "2000M",
                    "-f", "rawvideo", path], check=True)
    return load(path)


def load(path):
    n = os.path.getsize(path) // (W * H)
    if n <= SKIP + 10:
        raise SystemExit(f"只有 {n} 幀")
    return np.memmap(path, np.uint8, 'r', shape=(n, H, W))[SKIP:]


def assert_live(f, floor=0.20):
    """訊號必須是活的。靜止卡(No Signal / 回放 / 睡眠)的逐幀差恆為 0。"""
    d = np.array([np.abs(f[i + 1].astype(np.int16) - f[i]).mean()
                  for i in range(0, min(len(f) - 1, 40))])
    if d.mean() < floor:
        raise SystemExit(
            f"逐幀差平均只有 {d.mean():.4f} 位階(門檻 {floor})——"
            "擷取到的是靜止畫面,不是活的 live view。\n"
            "檢查:相機開著嗎?HDMI 接上了嗎?螢幕進入睡眠了嗎?"
            "是不是在回放或選單?")
    return d.mean()


def rect(f):
    """畫面矩形 —— 模式的獨立證據。3:2 與 16:9 分得出來(FHD 與 UHD 分不出來)。"""
    m = np.median(np.stack([f[i].astype(np.float32)
                            for i in range(0, len(f), max(1, len(f) // 12))]), axis=0)
    rows = np.where(m.max(axis=1) > 3.0)[0]
    cols = np.where(m.max(axis=0) > 3.0)[0]
    y0, y1, x0, x1 = rows[0], rows[-1], cols[0], cols[-1]
    return x0, x1, y0, y1, x1 - x0 + 1, y1 - y0 + 1


def events(s, floor_pct=1.5, floor_lvl=1.0, sigma=6.0):
    """6σ + MAD **加上絕對幅度下限**。

    只用 6σ 在極穩定的段落會失效:MAD 趨近 0,雜訊就被標成事件
    (2026-09-27 踩到,一個 5 秒段報 16 次但幅度只有 1.5%/8 mEV)。
    真事件是 ~3%(整幅)/~8%(陰影),所以 1.5% 的下限把雜訊擋掉而不會漏掉真的。

    **百分比下限不夠**:位階很低時(暗場景的陰影區可以低到 9.6)1.5% 只有
    0.14 位階,比量化階還小,雜訊照樣穿過去(2026-09-27 第二次踩到,
    一份 30 秒擷取報 75 次而它們全擠在 0.3 秒內)。真事件是 ~2.2 位階,
    所以同時要求絕對下限 1.0 位階。
    """
    m = np.median(s)
    mad = np.median(np.abs(s - m)) * 1.4826 + 1e-9
    drop = m - s
    hit = np.where((drop / mad > sigma) & (drop / m * 100 >= floor_pct)
                   & (drop >= floor_lvl))[0]
    # 叢聚收斂:真事件是**單幀**,一串連續命中是瞬變(場景/曝光變了、插拔),
    # 不是 N 個事件。0.5 秒內的命中算一個,取最深的那一幀。
    # (2026-09-27 踩了三次:一串 16/26/37/75 個「事件」都是同一個瞬變。)
    groups = []
    for k in hit:
        if groups and k - groups[-1][-1] <= 15:
            groups[-1].append(k)
        else:
            groups.append([k])
    peak = np.array([gp[int(np.argmax(drop[gp]))] for gp in groups], dtype=int)
    width = [len(gp) for gp in groups]
    return peak, [drop[k] / m * 100 for k in peak], m, width


def report(label, f):
    noise = assert_live(f)
    x0, x1, y0, y1, w, h = rect(f)
    print(f"   畫面矩形 {w}x{h} @ x{x0} y{y0}  比例 {w/h:.4f}"
          f"  ({'3:2 = OG3K' if abs(w/h-1.5) < 0.02 else '16:9 = FHD/UHD' if abs(w/h-1.778) < 0.02 else '?'})")
    cy, cx = slice(int(H * .12), int(H * .88)), slice(int(W * .12), int(W * .88))
    step = max(1, len(f) // 15)
    med = np.median(np.stack([f[i][cy, cx].astype(np.float32)
                              for i in range(0, len(f), step)]), axis=0)
    lo, hi = np.percentile(med, [0, 25])
    dark = (med >= lo) & (med <= hi)
    g = np.empty(len(f)); d = np.empty(len(f))
    for i in range(len(f)):
        fr = f[i][cy, cx]
        g[i] = fr.mean(); d[i] = fr[dark].mean()
    secs = len(f) / 29.97
    print(f"=== {label}   {len(f)} 幀 / {secs:.0f} 秒   訊號雜訊 {noise:.2f} 位階")
    for nm, s in (("整幅", g), ("陰影 最暗25%", d)):
        hit, amp, m, width = events(s)
        e = np.log2(np.maximum(s, 1))
        print(f"  {nm:12} 位階{m:6.2f}  事件 {len(hit):>3} 次 ({len(hit)/secs*20:5.1f} 次/20秒)"
              f"  幅度 {np.mean(amp) if amp else 0:5.2f}%"
              f"  最大單幀跳動 {np.abs(np.diff(e)).max()*1000:6.1f} mEV")
        if len(hit):
            print(f"               事件在第 {[round(k/29.97,1) for k in hit[:10]]} 秒"
                  f"  各佔 {width[:10]} 幀(1 = 單幀,才是閃爍;多幀 = 瞬變)")


if __name__ == "__main__":
    secs = float(sys.argv[1]) if len(sys.argv) > 1 else 20
    label = sys.argv[2] if len(sys.argv) > 2 else "擷取"
    tmp = os.environ.get("LVF_OUT", "/tmp/lvflicker.gray")
    report(label, grab(tmp, secs))
