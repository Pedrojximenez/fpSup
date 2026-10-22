#!/usr/bin/env python3
"""安全地停掉控制台 —— 一律用這支,不要自己 pkill。

踩過三次的坑:串流進行中把行程砍掉(或砍完沒等),相機還在推、host 沒人收
→ EP84 wedge,只能拔插 USB。正確順序是:
    1. /stream/stop  讓當前分段跑完(可能要等到一整段結束)
    2. 確認 shell 真的回來了
    3. 才 pkill
"""
import subprocess, sys, time, urllib.request, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor"))
import telemetry as T

def main():
    try:
        r = urllib.request.urlopen("http://localhost:8770/stream/stop", timeout=180).read()
        print("  stream/stop →", r.decode()[:80])
    except Exception as e:
        print("  stream/stop 沒回應(可能沒在跑):", e)
    for i in range(12):
        if T.health(timeout=15):
            print(f"  shell 已回復(第 {i+1} 次確認)")
            break
        print(f"  等 shell… {i+1}/12")
        time.sleep(5)
    else:
        print("  ★ shell 沒回來 —— 需要拔插 USB")
        return 1
    subprocess.run(["pkill", "-f", "fpstate.py"])
    time.sleep(2)
    print("  控制台已停止")
    return 0

if __name__ == "__main__":
    sys.exit(main())
