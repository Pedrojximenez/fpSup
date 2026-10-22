# SIGMA fp Ver.5.02 — 韌體完整性 / 簽章分析

**核心問題：韌體有無密碼學簽章驗證？能不能自製韌體？**

## 結論

**在整個韌體（IPL + 主韌體 + 全部四段）中，找不到任何密碼學簽章或雜湊驗證。**
完整性保護只有：

| 層級 | 機制 | 強度 | 可否偽造 |
|---|---|---|---|
| 更新容器（MAIN/IPL/PTBL/DAT1 各段） | `SUM=` = body **byte 累加和** mod 2³² | 純完整性 | ✔ 可任意重算 |
| 鏡頭韌體 `lensfirm.bin` | 每筆記錄 **CRC32** | 純完整性 | ✔ 可任意重算 |
| NAND 儲存 | **BCH ECC**（`BCH2K124`，`ECC Error!!`） | 錯誤更正，非安全 | 不適用 |

因此，**能夠正確重算 `SUM=` 的自製韌體，理論上會被機身接受**（更新流程未見任何拒絕未簽章映像的檢查）。

> 信心程度：**高**。理由見下方「為何這是決定性的」。單一保留點：IPL 的
> 「載入→搬移→執行」控制流未 100% 逐指令重建（Ghidra headless 對這顆
> bootloader 的函式/xref 還原不足，需要互動式作業）。但這**不影響結論**——原因如下。

## 為何這是決定性的（不依賴完整重建 IPL 控制流）

數位簽章（RSA-PKCS#1 / RSA-PSS / ECDSA / EdDSA）在**數學上必然**要對映像做
密碼學雜湊（SHA-1/256/512 之類）。因此「是否存在簽章驗證」可化約為
「是否存在雜湊原語」——而雜湊實作有**無法隱藏的常數表**。

我對「原始檔全部位元組」+「四段解開後的內容」做了雜湊/密碼輪常數表掃描：

```
SHA-256 K[0]=0x428a2f98   NOT FOUND
SHA-1   K0 =0x5A827999    NOT FOUND
SHA-1   K1 =0x6ED9EBA1    NOT FOUND
MD5     T[0]=0xD76AA478   NOT FOUND
SHA-512 K[0]             NOT FOUND
AES     S-box(63 7c 77 7b) NOT FOUND
AES     Te0=0xc66363a5    NOT FOUND
CRC32   table            FOUND (預期：鏡頭 CRC32 用)
```
（`工具：tools/scan` 系列，重跑指令見文末）

- **沒有任何 SHA / MD5 / AES 常數表** → 沒有標準簽章方案能運作。
- 密碼學關鍵字掃描：主韌體只有 `signed`（16×，實為 RTTI 型別 `signed int` 等）
  與 `ecc`（義大利文 *eccetto*、西班牙文 *selección*、NAND *ECC Error*）——**全為誤判**，
  逐一核對過上下文。無 `RSA`/`sign`/`verify sig`/`public key`/`certificate`/`mbedtls`/`openssl` 等。
- 主韌體的韌體標頭解析器 `analyze_firmware_bin_head_main` @ `0xC04CED60`
  只解析 `LENGTH= LOADADDRESS= OFFSET= VER= DVR= SUM= PID=`，驗證僅 byte-sum。
- IPL 只有 `Invalid Firmware?` / `invalid partition table (error code %d)` / `load error`
  這類**結構性**檢查字串，沒有任何雜湊/簽章字串或常數。

即使 IPL 內某處呼叫了 SoC mask ROM（IPL 透過 thunk 呼叫固定位址 `0x2E000428`，
即 XZ01 的 boot ROM），mask ROM 不在本韌體檔內、更新時也不會被改寫，
故它不可能對「使用者上傳的更新映像」做簽章把關而我們卻完全看不到雜湊資料流。

## 註記與界線

- 本結論針對 **Ver.5.02 這一版檔案**。
- 「找不到」是就**標準演算法的特徵**而言。理論上仍可能存在私有/混淆的完整性演算法，
  但那不是密碼學意義上的「簽章」，也無法阻止知道演算法者偽造（如同 `SUM=` 本身）。
- 這是**技術結構分析**，不是「刷機教學」。實際自製/改機仍涉及：正確的容器重打包、
  各段 checksum 重算、機身端更新流程的其他狀態檢查、以及變磚風險——這些未在此驗證。

## 重跑指令

```sh
cd /Users/dido/Developer/SIGMAfp_re
python3 - <<'PY'
import struct
files={'FULL':open('FP__V502.bin','rb').read(),
       'MAIN':open('out/seg0_c0000000.bin','rb').read(),
       'IPL':open('out/IPL.raw','rb').read(),
       'DAT1':open('out/DAT1.raw','rb').read()}
tabs={'SHA256':b'\x98\x2f\x8a\x42','SHA1':b'\x99\x79\x82\x5a','MD5':b'\x78\xa4\x6a\xd7',
      'AES_Sbox':b'\x63\x7c\x77\x7b\xf2\x6b\x6f\xc5','AES_Te0':b'\xa5\x63\x63\xc6'}
for n,p in tabs.items():
    print(n, {k:d.count(p) for k,d in files.items() if d.count(p)} or 'NOT FOUND')
PY
```
