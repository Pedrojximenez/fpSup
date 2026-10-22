# SIGMA fp (Ver.5.02) TK-OS Task-Creation ABI — VERIFIED

Read-only RE. Firmware `out/MAIN_c0000000.bin`, base 0xC0000000 (file off = addr − base).
Goal: recover + validate the task create/start ABI to build a minimal, SAFE heartbeat probe.

Evidence classes: **CONFIRMED** = read from disassembly/decomp/source. **ASSUMED** = needs a live probe.

---

## 0. Headline finding (CRITICAL) — the prior descriptor note is WRONG

The prior note claimed descriptor `[16..23]=name, [24]=0`. **That is incorrect.**
The real `cre_tsk` (FUN_c000c6b8) reads **descriptor+16 as the STACK SIZE (`stksz`)**, unconditionally.
The task NAME lives at **+20 (dsname[8])** and is copied **only if** `tskatr & 0x40` (TA_DSNAME) is set.

Consequently the ground-truth source `codex/stage6_gyro_double_buffer_hook.S`
(`start_writer_thread`, lines 312–343) is **malformed against the real ABI**:

```
[sp+16] = 0x57474653  ("S6GFWR" name, intended)   <-- firmware uses this as stksz = ~1.47 GiB
[sp+20] = 0x00003652                                <-- would be dsname[0..3], but ignored (tskatr=1, no 0x40)
tskatr  = 1 (no TA_DSNAME)  -> the intended name is never copied
```

`cre_tsk` performs **no bounds check** on `stksz` (pure bump allocator, §2), so create still
returns a valid positive task-id; the corruption is silent until `sta_tsk` launches the task
with an out-of-range stack pointer → near-certain crash and/or stack-pool corruption for all
later `cre_tsk` calls. This is exactly the "wrong/absent stack" top crash cause. **CONFIRMED.**

Net: do NOT copy stage6's descriptor. Use the corrected layout in §6.

---

## 1. Service IDs & dispatch — CONFIRMED

Syscall stub shape (`0xC01F885C`, disassembled):
```
stmdb sp!,{r4}; add r4,sp,#4; stmdb sp!,{lr}; ldr ip,[pc,#0xc]; bl 0xC00011D0; ...; bx lr
```
`ldr ip,[pc,#0xc]` loads a 32-bit **service ID** literal stored at stub+0x20:

| call      | stub addr   | service ID   | dispatched fn | note |
|-----------|-------------|--------------|---------------|------|
| cre_tsk   | 0xC01F885C  | 0x80470100   | 0xC000C6B8    | create task |
| sta_tsk   | 0xC01F8D90  | 0x80490100   | 0xC000C9D0    | start task  |
| del_tsk   | 0xC01F8934  | 0x80480100   | 0xC000C8E0    | delete task |
| ter_tsk   | 0xC01F8DB4  | 0x804A0100   | 0xC000CBB8    | terminate task |
| dly_tsk   | 0xC01F89C4  | 0x80460100   | 0xC000C3F0    | delay current task (r0 = ms) |

Dispatcher `FUN_c00011d0` (0xC00011D0, disasm) decodes the ID:
- ID is negative (bit31 set) → takes the SVC-trampoline path (saves APSR, bumps the
  dispatch-nesting counter at DAT_c000150c). This is the normal **task-context** system-call entry.
- `sl = (ID >> 16)` sign-extended = function-table index. Table base = word@0xC0001568 = **0xC0021040**.
  `fn = *(0xC0021040 + sl*4)`. For 0x8047→0xC000C6B8, 0x8049→0xC000C9D0 (verified numerically).
- `(ID>>8)&0xff` = parameter-word count (0x01 here). Special-cased ==5 path derefs r4.

Strings cross-confirm the family: `cre_tsk error !! %d`, `sta_tsk error !! %d`,
`%s() ext_tsk`, `tkos task chgpri [tskid] [priority]` (out/MAIN.strings.txt:15549,15550,11277,15984).

---

## 2. cre_tsk (0xC000C6B8) — descriptor layout & stack handling — CONFIRMED

From decomp blk_c00.c:9602–9686 and disasm 0xC000C6B8–0xC000C8D8. `param_1` = descriptor ptr.

Descriptor (T_CTSK-like), word indices:
| off  | field      | firmware use | validation |
|------|------------|--------------|------------|
| +0   | exinf      | TCB[0] = extended info | none |
| +4   | tskatr     | attributes   | `(tskatr & 0xFFFFFFB8)==0` else **E_RSATR (-11)**. Only bits 0x01,0x02,0x04,0x40 allowed |
| +8   | task       | entry point  | must be **≠0** else E_PAR (-17) |
| +12  | itskpri    | priority     | must be **≠0** else E_PAR (-17) |
| +16  | **stksz**  | **stack size** (bump-allocated) | **no bound check** |
| +20  | dsname[8]  | DS object name | copied to TCB+0x2c **only if tskatr & 0x40 (TA_DSNAME)** |

tskatr bits observed:
- 0x01 = TA_HLNG (C entry). stage6 uses this.
- 0x02 = user-supplied stack buffer path (`tst r3,#2`): if set with stksz≠0, calls FUN_c000d990
  with a caller buffer @ descriptor+0x14; if stksz==0 uses inline. (T-Kernel TA_USERBUF-like.)
- 0x40 = TA_DSNAME (enables +20 name copy).

Stack allocation, **normal path** (tskatr bit1 = 0, disasm 0xC000C848):
```
stksz = param_1[4]                                  // descriptor+16
stack_lo = _DAT_c301eae4 + stksz + 1                // 64-bit pool base @ 0xC301EAE4/EAE8 (RAM/BSS)
TCB[+0x1c/+0x20] = stack_lo/hi ; TCB[+0xc] = 0
return_id = (TCB - 0xC301EACC)/0x34 + 1             // task-id, TCB stride 0x34 (52 bytes)
```
→ **The OS allocates the stack from a pool; the caller must supply a sane `stksz` at +16.**
No E_LIMIT/E_NOMEM guard on stksz was found — a garbage size is accepted and only bites at run time.

Return: **task-id ≥ 1** on success; negative T-Kernel error otherwise
(E_RSATR -11, E_PAR -17, E_LIMIT -34 (-0x22) if TCB free-list empty). **CONFIRMED.**

del_tsk (0xC000C8E0, decomp 9693–9736): arg r0 = tskid (valid 1..0x32); unlinks TCB, returns it to
the free-list (DAT_c301eaf8), marks slot free. Returns 0 / E_ID(-18) / E_NOEXS(-42, 0xffffffd6).
Note: the normal-path stack pool bump is **not** reclaimed here → repeated create/delete leaks the
stack pool. Fine for a one-shot probe. **CONFIRMED.**

---

## 3. sta_tsk (0xC000C9D0) — CONFIRMED

Disasm 0xC000C9D0. `r0 = tskid`. Validates `(id-1) < 0x32` else E_ID(-18); TCB entry[+8]≠0 else
E_NOEXS(-42, -0x29→…); state[+0xc]&1 check (already-active → error). Loads the task stack from
TCB[+0x1c/+0x20] (the value cre_tsk stored) and makes the task runnable.
Return: 0 (E_OK) / negative. `r1` = start code (stacd) — unused for direct-entry, may be junk.
stage6 calls it with r0 still holding the create'd id (line 336–340). **CONFIRMED.**

---

## 4. ter_tsk (0xC000CBB8) — CONFIRMED

Disasm 0xC000CBB8. `r0 = tskid` (1..0x32, else E_ID). Requires TCB exists (entry[+8]≠0 else
E_NOEXS). Checks active state[+0xc]&1, unlinks from wait queues ([+0x14]). Forces the task dormant.
Return 0 / negative. Use before del_tsk for a running task. **CONFIRMED.**

(0x804B → 0xC000CC98 takes 2 params (r0=id, r1) = chg_pri/rel-wait family; not needed.
ext_tsk = self-exit-current-task exists per strings but was not needed and not isolated to a
single-param 0x804x stub; the ter+del path below is the clean external-cleanup route.)

---

## 5. dly_tsk / cooperative sleep — CONFIRMED

stage6 `writer_sleep` calls helper **0xC03705D8** with r0 = 5. That helper (disasm) forwards r0 to
stub 0xC01F89C4 (service 0x80460100 → FUN_c000c3f0 = **tk_dly_tsk**), i.e. delay current task r0 ms,
and logs on error. Use `0xC03705D8` (r0 = milliseconds) to yield inside the heartbeat loop.
**CONFIRMED.**

---

## 6. VALIDATED heartbeat-probe spec

### Descriptor bytes to build (32-byte stack buffer; 20 bytes used, no TA_DSNAME)
```
[+0]  exinf   = 0x00000000
[+4]  tskatr  = 0x00000001          ; TA_HLNG (C/ARM direct entry). NO 0x40, so no name field.
[+8]  task    = <entry addr>        ; ARM: even addr; Thumb: addr|1. MUST be nonzero.
[+12] itskpri = 0x0000003C          ; 60 — value stage6 *statically chose* (NOT proven at runtime;
                                    ; only "passes cre_tsk / nonzero" is CONFIRMED, see §7). MUST be nonzero.
[+16] stksz   = 0x00002000          ; 8 KiB. **THIS is the field stage6 got wrong.** CONFIRMED slot.
[+20] (unused, leave 0)
```
Keep stksz modest (4–8 KiB); the pool bump is not freed on the normal path.

### Call sequence
```
r0 = &descriptor
blx 0xC01F885C            ; cre_tsk  -> r0 = task_id (>=1) or negative error
cmp r0, #1 ; blt fail     ; (stage6 line 336–337 pattern)
; r0 still = task_id
blx 0xC01F8D90            ; sta_tsk(r0=id) -> 0 / negative
```
Heartbeat task body: `loop { counter++; r0=<ms>; blx 0xC03705D8; }` (e.g. 100 ms), optionally
checking a stop flag in a fixed RAM word so it can self-terminate by falling out of the loop.

### Bounded cleanup (external context holding the saved id)
NOTE (2026-08-19, Codex): the 0xC01F8DB4 / 0xC01F8934 pair below is the **Cyc subsystem** ter/del
(services 0x804A/0x8048) and must NOT clean up a task created via the main path (0x8001). Use the
**main-path** cleanup instead: **tk_ter_tsk 0xC01F8E64 (0x80060100)**, **tk_del_tsk 0xC01F8978
(0x80020100)**, called from another live task. Main-path stack-pool reclamation is unverified.
`tk_ext_tsk` (self-exit) is service family 0x80040000; callable stub not yet isolated.
```
(Cyc, do NOT use for main-path tasks:) r0=id; blx 0xC01F8DB4  ; Cyc ter_tsk
                                        r0=id; blx 0xC01F8934  ; Cyc del_tsk
```

### Stack handling summary
- **OS-allocated** from an internal pool (normal path, tskatr bit1=0). Caller supplies only `stksz`
  at descriptor+16. Caller does NOT supply a stack pointer (that path needs tskatr 0x02 + buffer).
  CONFIRMED.

### Context constraints — ASSUMED (NOT hardware-proven)
- These are negative-ID system calls routed through the FUN_c00011d0 SVC trampoline; expected safe
  from normal task/thread context. Stage6 *statically* issues cre/sta from a gyro-thread-hooked
  path, but **stage6 was never run on hardware** (see §0 / STAGE6_DOUBLE_BUFFER_DESIGN: "尚未部署實機"),
  so this is ASSUMED, not CONFIRMED. The gyro-thread hook (0xC00D0794) as a *safe context to issue
  sta_tsk from* is itself unproven — a live probe (this session) shows create OK / start FREEZES.
- Must NOT be issued from a true ISR / task-independent portion (standard T-Kernel rule; the
  trampoline manipulates the dispatch-nesting counter and expects task context). ASSUMED-standard.

---

## 7. Direct answers

**Is it safe to write a minimal heartbeat-task probe with this ABI?**
The create→start→(ter+del) sequence and descriptor layout are recovered from disassembly/decomp and
are internally consistent — worth probing. But stage6 was **never run on hardware**, so it is NOT
evidence the pair works; it is a static template only. Use the **corrected** descriptor in §6
(stksz at +16), not stage6's.

**LIVE PROBE RESULT (this session, 2026-08-18/19) — ✅ RESOLVED.**
Sequence: A1 create-only (Cyc cre_tsk 0xC01F885C) → id 14, mem-save survives. A/A2 add Cyc sta_tsk
(0xC01F8D90) → FREEZE, no readback. **Root cause: WRONG subsystem.** 0xC01F885C/0xC01F8D90 (service
0x8047/0x8049) are the **Cyc-thread** create/start (the Cyc wrapper 0xC0370808 always passes stksz=0 +
entry=fixed trampoline 0xC0370BF0); using them with a DIRECT entry corrupts on start.
The **main task path** (shell, CamMain, LcdTh) uses **tk_cre_tsk 0xC0016A58 (service 0x80010100 →
FUN_c000a9c0)** + **tk_sta_tsk 0xC0016BC0 (service 0x80030200)**. FUN_c000a9c0 validates: itskpri
**1..32** (else E_PAR −17), stksz **≥0x100**, tskatr allowed-mask 0x361 (else E_RSATR −11).
Probe **A4** (main path, itskpri=100) → clean E_PAR, **NO FREEZE**. Probe **A5** (itskpri=28) →
**id 119, start 0, 'WORK', heartbeat 145/1500ms (~10ms/iter), NO FREEZE = first self-created task
running live.** Priority hypothesis refuted (shell=25, gyro=20; 0x3C=60 is *below* both). Full recipe:
see notes/research/rtos/TASK_PRIORITY_MAP.md and the comm repo docs/TASK_ABI_STATUS.md.

**Single most likely failure mode to watch for:**
A bad/oversized `stksz` at descriptor+16. cre_tsk does no bounds check and still returns a valid
task-id, so the fault only appears when sta_tsk launches the task on an out-of-range stack →
immediate crash and/or corruption of the shared stack pool (0xC301EAE4) affecting later
task creation. This is precisely the bug baked into stage6's descriptor. Set stksz = 0x2000 and
verify create's return is ≥1 before starting.

### What still needs a LIVE probe (ASSUMED)
- Absolute valid range / config cap for `itskpri` (only "≠0" is enforced in cre_tsk; 0x3C is NOT
  "known good" — it only passes cre_tsk, and its relation to the shell/AutoRun task priority is
  UNKNOWN, so it may starve the shell). Recover shell + gyro-thread priorities to set worker below them.
- That an OS-pool 8 KiB stack is actually sufficient for the chosen entry (trivial loop: yes).
- ISR-context prohibition (standard, not disproven here).
- Exact `ext_tsk` stub if self-exit (rather than external ter+del) is preferred.
