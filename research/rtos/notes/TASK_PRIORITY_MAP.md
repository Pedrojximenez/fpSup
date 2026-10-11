# SIGMA fp (Ver.5.02) TK-OS Task PRIORITY Map

Read-only static RE. Firmware `out/MAIN_c0000000.bin`, base 0xC0000000 (file off = addr − base).
Goal: pick a background-worker `itskpri` strictly BELOW the AutoRun/shell task and the gyro thread.
µITRON convention: **lower number = higher priority** (priority 1 = highest).

Evidence: **CONFIRMED** = read from disassembly. **INFERRED** = deduced/dynamic-can't-fully-pin.

---

## 0. CORRECTION to the prior known-fact (important)

The brief said "the only direct caller of cre_tsk stub 0xC01F885C is 0xC0370878." That is true but
**that stub is NOT the main task-create path.** There are TWO task-create syscall stubs, both
routing through the dispatcher FUN_c00011d0:

| service ID   | stub        | used by                                   |
|--------------|-------------|-------------------------------------------|
| 0x80470100   | 0xC01F885C  | ONLY the "Cyc-thread" wrapper 0xC0370808  |
| **0x80010100** | **0xC0016A58** | **the MAIN path** — inline descriptors + the 44-entry master task table |

Both consume the same descriptor layout (+0 exinf,+4 tskatr,+8 entry,+12 itskpri,+16 stksz,+20 dsname[8]).
`0xC0016A58` is a stub of identical shape; its service-ID literal at 0xC0016A78 = **0x80010100** (CONFIRMED).

So the real task universe = {16 Cyc threads via 0xC0370808} ∪ {inline-descriptor tasks via 0xC0016A58}
∪ {44 tasks from the master table, created via the table-creator FUN_c036eca8 → 0xC0016A58}.

---

## 1. The Cyc-thread WRAPPER 0xC0370808 — CONFIRMED

Prologue at **0xC0370808** (contains the 0xC0370878 `bl cre_tsk`). Disasm:

```
c0370808 push {r4,r5,r6,r7,lr}; sub sp,#0x1c
c0370810 mov r4,r0 / r5,r1 / r6,r2 / r7,r3      ; r0=this,r1=name,r2=prio,r3=entry
c0370828 str <0xc0b990f4>,[r4,#8]               ; this+8 = class vtable
c0370830 str #0,[r4] ; str r7,[r4,#4]           ; this+4 = entry (r3)
c0370838 memset(sp,0,0x1c)                       ; zero descriptor
c0370850 str <0xc0370bf0>,[sp,#8]               ; descriptor+8  = entry = FIXED trampoline 0xC0370BF0
c0370854 str r4,[sp]                            ; descriptor+0  = exinf = this
c0370858 str #0x41,[sp,#4]                      ; descriptor+4  = tskatr = 0x41 (TA_HLNG|TA_DSNAME)
c0370860 str r6,[sp,#0xc]                       ; descriptor+12 = itskpri = r6 = 3rd arg  <====
c0370870 memcpy(sp+0x14, r5, 8)                 ; descriptor+20 = dsname = 2nd arg (8 bytes)
c0370874 mov r0,sp ; c0370878 bl 0xC01F885C     ; cre_tsk
c0370880 str r0,[r4]                            ; this+0 = task-id
```

**Signature:** `Thread_start(void* this /*r0*/, char name[8] /*r1*/, int itskpri /*r2*/, void* entry /*r3*/)`.
It BUILDS the descriptor from its args. **itskpri = the 3rd argument (r2).** CONFIRMED.
Note: descriptor+16 (stksz) is left **0** by this wrapper — the trampoline path relies on the
per-object stack; the entry is always the fixed trampoline 0xC0370BF0 which does
`r0=this; if(this+4) blx this+4 else blx (*(this_vtable+0xc))`. (So the real body runs via this+4.)

---

## 2. PRIORITY DISTRIBUTION

### 2a. Cyc-thread tasks (wrapper 0xC0370808, service 0x8047) — CONFIRMED
caller → itskpri (dec/hex) → name (dsname, read from r1 target):

| caller_addr | prio dec | hex  | name       |
|-------------|----------|------|------------|
| 0xC068336C  | 2        | 0x02 | MONITCYC   |
| 0xC02DD1B4  | 14       | 0x0E | KeyChat    |
| 0xC04D8AEC  | 16       | 0x10 | Uvc16ms    |
| 0xC0527990  | 16       | 0x10 | CYC_DRAW   |
| 0xC00D0650  | 20       | 0x14 | GyroCycl   |
| 0xC04D8AD4  | 33       | 0x21 | Uvc33ms    |
| 0xC05BFCD0  | 33       | 0x21 | DngPlayT   |
| 0xC0395DD0  | 50       | 0x32 | RECMGRMV   |
| 0xC04C9B40  | 50       | 0x32 | OSD_CYC    |
| 0xC00D1340  | 100      | 0x64 | EXT_EVF    |
| 0xC0308C5C  | 100      | 0x64 | LCDAUTO    |
| 0xC0514DA4  | 100      | 0x64 | TimerEvt   |
| 0xC0304538  | 500      | 0x1F4| FACECYC    |
| 0xC0306A4C  | 625      | 0x271| DISPSATU   |
| 0xC05186CC  | 1000     | 0x3E8| TIMWATCH   |
| 0xC002AEEC  | dynamic  | —    | LED_CYC (prio = `ldrh [obj+4]`, INFERRED) |

Each read from a `mov r2,#imm` / `movw r2` immediately before the `bl 0xC0370808` (CONFIRMED).

### 2b. Master task TABLE @ 0xC0B97F90 — CONFIRMED
Table-creator FUN_c036eca8: 44 entries × 0x20 bytes; per-entry itskpri@+0xc, stksz@+0x10,
dsname@+0x14 (entry field points to fixed trampoline 0xC036EE50). Created via 0xC0016A58.
Callers pass an index (r1) to FUN_c036dd40→FUN_c036eca8.

| idx | prio | stksz  | name     | idx | prio | stksz  | name     |
|-----|------|--------|----------|-----|------|--------|----------|
| 0   | 16   | 0x4000 | RecPMgr  | 22  | 13   | 0x2800 | EventMgr |
| 1   | 12   | 0x1000 | RecPTmr  | 23  | 9    | 0x1000 | TP       |
| 2   | 9    | 0x4000 | SRecMgr  | 24  | 17   | 0x4000 | DrawMgr  |
| 3   | 15   | 0x5000 | SRecRaw  | 25  | 14   | 0x2000 | AeDev    |
| 4   | 16   | 0x4000 | SRecYuv  | 26  | 14   | 0x4000 | AfMgr    |
| 5   | 16   | 0x4000 | SRecJpeg | 27  | 14   | 0x1000 | AeIris   |
| 6   | 6    | 0x4000 | SRecFile | 28  | 16   | 0x1000 | Level    |
| 7   | 16   | 0x4000 | PlyMgr   | 29  | 16   | 0x1000 | Poff     |
| 8   | 15   | 0x4000 | MRecMgr  | 30  | 16   | 0x400  | KeyMon   |
| 9   | 16   | 0x1000 | CamMgr   | 31  | 13   | 0x800  | PlayEve  |
| 10  | 16   | 0x1000 | WiFiMgr  | 32  | 17   | 0x1000 | EyeDtctn |
| 11  | 16   | 0x2500 | Sdcard   | 33  | 17   | 0x2000 | Tracking |
| 12  | 16   | 0x2500 | SdHost   | 34  | 22   | 0x4000 | PlaySub  |
| 13  | 15   | 0x4000 | CamSch   | 35  | 13   | 0x2000 | PicCorr  |
| 14  | 7    | 0x2000 | ImgCtrl  | 36  | 16   | 0x400  | UserTim  |
| 15  | 16   | 0x1000 | BtrMgr   | 37  | 10   | 0x2000 | PFileR   |
| 16  | 11   | 0x1000 | LedBlink | 38  | **20** | 0x2000 | **GyroData** |
| 17  | 16   | 0x1000 | ExtStrb  | 39  | 16   | 0x2000 | ImgCorr  |
| 18  | 16   | 0x1000 | ESCycl   | 40  | 15   | 0x2000 | QrRead   |
| 19  | 10   | 0x1000 | Strb     | 41  | 26   | 0x2000 | QrReadE  |
| 20  | 12   | 0x4000 | usbctrl  | 42  | 14   | 0x2000 | AfIfMgr  |
| 21  | 14   | 0x4000 | usb_ds   | 43  | 18   | 0x1000 | GpsMgr   |

### 2c. Inline-descriptor tasks (direct 0xC0016A58) — CONFIRMED
| caller      | prio | entry      | stksz  | name    |
|-------------|------|------------|--------|---------|
| 0xC0016744  | 20   | 0xC00207F8 | 0x8000 | CamMain |
| 0xC02E622C  | 8    | 0xC02E6748 | 0x2000 | LcdTh   |
| 0xC02DBFD0  | 14   | 0xC02DC0A8 | 0x500  | DevOpe  |
| 0xC0033A68  | 12   | 0xC0033B80 | 0x4000 | (—)     |
| 0xC0035E7C  | 28   | 0xC00379D8 | 0xC800 | (—)     |
| 0xC0340628  | 10   | 0xC03405C0 | 0x2000 | (—)     |
| 0xC0342150  | 12   | 0xC03420E0 | 0x2000 | (—)     |
| 0xC0346200  | 10   | 0xC03461A0 | 0x2000 | (—)     |
| 0xC0347468  | 10   | 0xC0347408 | 0x2000 | (—)     |
| 0xC034E1E0  | 11   | 0xC034E278 | 0x2000 | (—)     |
| 0xC0352838  | 10   | 0xC0350A00 | 0x3000 | (—)     |
| 0xC0352898  | 10   | 0xC03520F8 | 0x2000 | (—)     |
| 0xC0352928  | 10   | 0xC0352410 | 0x2000 | (—)     |
| 0xC0352988  | 16   | 0xC0352758 | 0x1000 | (—)     |
| 0xC035C068  | 11   | 0xC035C460 | 0x2000 | (—)     |
| 0xC0409478  | 6    | 0xC0409600 | 0x2000 | sdcard5 (ROM template @0xC0BC20C4) |
| 0xC0031ED0  | dynamic (`[reftsk]-1`) | 0xC0031E18 | 0x600 | (transient) INFERRED |
| **0xC03DA258** | **25** | **0xC03DA118** | **0x4000** | **shell** ← AutoRun/shell task |

(0xC036DFDC / 0xC036F88C / 0xC036EDC8 are the internal generic constructors themselves — the
table-creator and two dynamic helpers whose prio/stksz come from object fields; not distinct tasks.)

---

## 3. SHELL / AutoRun task PRIORITY = 25 (0x19) — CONFIRMED

- Command table @0xC0BAC14C, dispatcher FUN_c03d9c20, AutoRun runner FUN_c03da758 (per SHELL_COMMANDS.md).
- The **shell task** is created inside **FUN_c03da178** (the shell setup, called synchronously during
  boot-init at 0xC0021190 → thunk 0xC0020B70 → `bl 0xC03DA178`). FUN_c03da178 builds a descriptor on
  its own stack and calls cre_tsk stub 0xC0016A58 at **0xC03DA258**:

```
c03da1d0 str #0,[sp,#0x24]      ; exinf
c03da1d8 str #0x41,[sp,#0x28]   ; tskatr = 0x41
c03da1f4 str <0xc03da118>,[sp,#0x2c] ; entry = 0xC03DA118 (command loop)
c03da1e0 str #0x19,[sp,#0x30]   ; itskpri = 0x19 = 25   <====
c03da1e8 str #0x4000,[sp,#0x34] ; stksz = 0x4000
c03da208 memcpy(sp+0x38, <0xc0babdac="shell">, 8)  ; dsname = "shell"
c03da254 add r0,sp,#0x24 ; c03da258 bl 0xC0016A58   ; cre_tsk -> id
```

Descriptor name literal @0xC0BABDAC = `"shell"`. **Shell/AutoRun task itskpri = 25 (0x19).** CONFIRMED.

---

## 4. GYRO thread PRIORITY = 20 (0x14) — CONFIRMED

The gyro object init **FUN_c00d0600** registers itself as master-table index **0x26 = 38**:
```
c00d0610 mov r1,#0x26 ; c00d0614 bl 0xC036DD40   ; FUN_c036dd40(gyroObj, idx=38) -> FUN_c036eca8
```
Master table[38] = **"GyroData", itskpri = 20 (0x14)**, stksz 0x2000 (§2b, CONFIRMED).

The hook site **FUN_c00d0738** (0xC00D0794) is the gyro-data handler; it is reached by the chain
0xC00D0700 → 0xC00D0710 → `bl 0xC00D0738`, and the pointer 0xC00D0700 lives in the gyro object's
vtable-struct @0xC074A054 (adjacent to the "GyroCycl" name @0xC074A058). So FUN_c00d0738 executes in
the **GyroData task context, priority 20**. The separate "GyroCycl" Cyc thread (§2a, 0xC00D0650) is
**also priority 20**. Either way **gyro = 20 (0x14).** CONFIRMED.

---

## 5. VALID PRIORITY RANGE — no small cap found; effective range ≥ 1..1000

- **cre_tsk (FUN_c000c6b8):** validates itskpri only `≠0` (0xC000C6DC `ldrne r0,[r5,#0xc]; cmpne r0,#0`
  → E_PAR −17 if 0). Stores it to **TCB+0x10** (0xC000C768 `str r0,[r4,#0x10]`). **No upper-bound check.** CONFIRMED.
- **chg_pri (FUN_c000cc98):** validates only the task-id (`sub r0,#1; cmp #0x32` → max **50 tasks**);
  **no priority upper-bound compare.** CONFIRMED.
- **sta_tsk (FUN_c000c9d0):** task-id `< 0x32`; makes the task runnable via 0xC000D990; the ready
  structure is a **priority-sorted/delta list**, not a fixed `TMAX_TPRI` array — no per-level array
  bound to read off. INFERRED (no bounded ready-queue array located).
- **Empirical:** active priorities in use span **2 … 1000** (MONITCYC=2 … TIMWATCH=1000), all coexisting.

**Conclusion:** no `CFG_MAXTSKPRI` small constant is enforced anywhere in the create/start/chgpri path;
the field is a sort key. Any positive value ≤ ~1000 is safely accepted (1000 is demonstrably valid).
Max task **count** is 0x32 = 50 TCB slots (separate limit). CONFIRMED (only ≠0 enforced) / INFERRED (no array cap).

---

## 6. RECOMMENDATION — background-worker itskpri = **0x64 (100 decimal)**

Requirement: strictly lower priority (numerically higher) than BOTH shell (25) and gyro (20)
→ number must be **> 25**. Recommended **itskpri = 0x64 (100)**:
- 100 > 25 (shell) and 100 > 20 (gyro) → worker is strictly below both; it cannot starve the shell. ✔
- 100 is a **proven in-use level** (EXT_EVF / LCDAUTO / TimerEvt), so definitely within valid range. ✔
- It sits below the shell (0x19) and the gyro/GyroData (0x14) — the two priorities it must sit under.

Alternative: **0x3C (60)** also satisfies the ordering (60 > 25 and 60 > 20) and is closer to mid-range
if you want the worker to run a bit more eagerly. Do NOT use ≤ 25 (would meet/exceed the shell) or 0
(rejected by cre_tsk).

> Note: this refutes the earlier freeze hypothesis "worker prio 0x3C higher than shell." 0x3C=60 is
> LOWER priority than shell(25), so it could not have starved the shell — the freeze cause lies
> elsewhere (stksz / sta_tsk startup, not priority ordering).

---

## Opportunistic: sta_tsk startup frame / descriptor fields

cre_tsk reads only descriptor **+0..+0x1b** (exinf→TCB+0, tskatr→+4, entry→+8, itskpri→+0x10,
stksz used for pool bump, dsname→TCB+0x2c if tskatr&0x40). **No descriptor field beyond +20 is read,
and no initial return address is stored in the descriptor.** For the Cyc wrapper, the task entry is
the fixed **trampoline 0xC0370BF0** whose epilogue is `pop {r4,pc}` — so a body that RETURNS unwinds
back through the trampoline (task-return is handled). Raw inline-descriptor tasks (e.g. shell entry
0xC03DA118) have the real function as entry directly, with **no OS-installed return handler in the
descriptor** — such a task returning from its entry is not explicitly caught by cre_tsk's setup.
