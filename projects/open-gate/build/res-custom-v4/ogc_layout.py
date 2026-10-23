"""res-custom, the multi-format OpenGate core (32RESCUS.BIN): one layout, one source of truth.

notes/OG_MULTIFORMAT_CORE_DESIGN.md §3.2 (virtual profile, virtual mode).

The layout is a coordinate system (og_pic.inc, OG_V3_PAIR): the shims are
assembled at LAYOUT0, the state S sits at S_COORD after them.  Inside S every
reference is an OFFSET from S -- no absolute address is stored in the image, so
nothing has to be relocated; the entry (ogc.c) only fills the run-time words
(C function addresses, the picker entries' key pointers, which rows are on).

`header()` writes ogc_layout.h for ogc.c and ogc_shims.S; `state_blob(rows)`
builds S for the given format rows.  Python, C and assembly read the same
numbers.
"""
import os
import struct

LAYOUT0 = 0xC0730000          # the coordinate origin (og_pic.inc OG_CAVE0)
# Diagnostic build (env OGC_HOOKCNT=1): every hook site enters through a counting
# stub (hookcnt[i] += 1) appended to the shims; the shims' window grows to hold them.
HOOKCNT = os.environ.get('OGC_HOOKCNT') == '1'
SHIMS_MAX = 0x2400 if HOOKCNT else 0x1400
HOOKCNT_BACK = 0x100          # the counters: the shims' window's last 64 words (zero in the image)
CAP_BACK = 0x400              # with HOOKCNT: the last virtual-profile record, before/after ogc_canvas
RESERVED_BACK = CAP_BACK if HOOKCNT else 0   # the shims' code stays below this
S_COORD = LAYOUT0 + SHIMS_MAX
MAGIC, VERSION = 0x3143474F, 1    # "OGC1"

# ---- S: the core's state, offsets from S -------------------------------------
S = dict(
    MAGIC=0x000, VERSION=0x004,
    FLAG=0x008,          # 1 = an OG row is live (chosen AND CinemaDNG): asm reads it
    ASPECT=0x00C,        # 0, or the live row's aspect enum when FLAG && PICKOK: asm reads it
    CUR=0x010,           # live row + 1, 0 = none
    RESVAL=0x014,        # the resolution value the setter last saw (always stock: 2 or 3)
    FMTLATCH=0x018,      # 0 = CinemaDNG; boot value UNKNOWN
    BITLATCH=0x01C,      # eRawBitType of the last picker hit (0, 3, 4)
    PICKOK=0x020,        # 1 = the picker agreed with the menu
    FPSLATCH=0x024,      # canvas +0x030 of the last hit (float bits), 0 = none yet
    PBROW=0x028,         # row + 1 whose DNG size the name emitter last saw (playback)
    LAST_ENT=0x02C,      # offset of the last picker hit, 0 = none
    NROWS=0x030, ROWS=0x034, NENT=0x038, ENTS=0x03C, NVM=0x040, VMS=0x044,
    VPID0=0x048,         # first virtual profile id (row r has VPID0 + r)
    VMID0=0x04C,         # first virtual mode id (vm v has VMID0 + v)
    HITS=0x050, OUT_HITS=0x054, SEL_COUNT=0x058, LOOK_HITS=0x05C,
    RLOG=0x060,          # 8 words: restore log (as og3krestore's RLOG)
    FN=0x080,            # 32 words: C entry points, absolute, filled by the entry
    OLDFN=0x100,         # 16 words, free since FN moved to 0x080
    BINFILT=0x100,       # six per-row packed CRCT recipes; 0 = original behavior
    TPL0=0x140, TPL2=0x170,   # og3kout's two templates: +0 built, +4.. 44 bytes
    PAIRS=0x1A0,         # 8 {value, row} pairs: the resolution converter's table (C06BDA3C/40/48)
    BASEROW=0x1E0,       # 8 words: virtual pid -> base row (mapping index); asm reads
    # §13: the Quick Set (scheme B) -- the record, layout and pack layers
    QS_TAB=0x200,        # the recipe table (uishare ui/qs.py encode()), absolute
    QS_N=0x204,          # rows in the resolution list, read at the first record (0 = not yet)
    QS_READY=0x208,      # 1 = the layers may edit; 2 = N unsupported (pass everything)
    QS_DEPTH=0x20C,      # nested record parses using a copy buffer now
    QS_BUF=0x210,        # QS_SLOTS x 2 x QS_CAP bytes of copy buffers, absolute
    QS_PRE=0x214,        # the layout UicResourceCache held when the hooks went up
    QS_BOOT=0x218,       # 1 = the one boot re-parse is done (or not needed)
    QS_INRELOAD=0x21C,   # 1 while we run v3 + v2 (a layout load inside ours)
    SEL=0x220,           # §12: the chosen row + 1 (0 = a stock row); the menu's commit callbacks set it
    DIRTY=0x224,         # the BIN record no longer says SEL
    PATH=0x228,          # this file's path (entry r2), absolute
    CFG=0x22C,           # the BIN settings area in the block (block + 32), absolute
    FOBJ=0x230,          # a 0x1000-byte file-object scratch in the block tail, absolute
    PAIRN=0x234,         # pairs in PAIRS
    SAVES=0x238, SAVE_FAILS=0x23C,
    VMDONOR=0x240,       # 16 words: virtual mode -> donor id; asm reads
    QS_HITS=0x280, QS_PASS=0x284, QS_ERR=0x288, QS_RELOADS=0x28C, QS_PACKFAIL=0x290,
    QS_FULL=0x294,       # records passed down because every copy buffer was in use
    # §14: what the entry found in \fpSup\RESCUS
    RCD_FOUND=0x2A0,     # .RCD names seen
    RCD_OK=0x2A4,        # of them valid
    RCD_BAD=0x2A8,       # bit i: the i-th name (sorted) was refused
    RCD_WHY=0x2AC,       # the first refusal: (name index << 16) | reason
    DATA=0x2B0, DATA_CAP=0x2B4, DATA_USED=0x2B8,   # the files' area in the block, absolute
    ENABLE_FN=0x2BC,     # ogc_enable_set (consumer-owned settings), absolute
    NAVAIL=0x2C0,        # valid formats on the card (all of them, enabled or not)
    AVAIL=0x2C4,         # 16 x 8-byte labels, sorted by file name
    S_END=0x344,         # bytes S uses (rows, entries, lists, overrides, vms) -- offset
    UI_OK=0x348,         # rows whose menu (uia_apply) went in
    RCD_WHYS=0x350,      # 16 bytes: each looked-at name's outcome (0 = a row, else RCD_WHY)
    # the virtual table (2026-10-07): every picker entry names a (mode, profile) of its own
    POOL=0x360,          # 32 words: the virtual profile ids, in the order variants take them
    NVAR=0x3E0,          # variants in VARS
    VARS=0x3E4,          # offset of the variant table {pid, base row, row, list offset} (VAR_*)
    UIA_FN=0x3E8,        # uishare's uia_apply (absolute; the entry calls it through here)
    LVOWED=0x3EC,        # 1: the setter changed our live row but not the camera's value -> LV reload after it
    LV_RELOADS=0x3F0,
    EXCLOWED=0x3F4,      # 1: our live row changed -> recompute the frame-rate list class after the setter
    EXCL_RECOMPUTES=0x3F8,
    SAVE_WHY=0x3FC,      # the last refused / failed BIN write: 1 file gone, 2 not this sup, 3 I/O
    NEXT=0x400,          # 64 words: each hook's way down (chain_next or replay)
    # the virtual frame rates (K = 4: 239.76, 279.72 on 119.88; 17.98, 8.99 on 23.98)
    RPAIRS=0x600,        # 16 {internal, row} pairs: the frame-rate converter (C06BDB0C/10/18)
    SPAIRS=0x680,        # 12 {export, summary state} pairs: the summary converter (C06CB6DC/E0/E8)
    VRATE=0x6E0,         # the virtual rate chosen (fps x 100) while the live row has entries for it, 0 = none
    RPAIRN=0x6E4, SPAIRN=0x6E8,
    VR_UI=0x6EC,         # 1: the menu rows went in
    VR_WHY=0x6F0,        # the menu install: 1 in, else why not
    VR_COMMITS=0x6F4,
    RATE_LVOWED=0x6F8,   # native enum + 1: virtual cadence changed on the same carrier; reload after commit
    RATE_LV_RELOADS=0x6FC,
    VR_LABEL=0x700,      # K string ids: the labels (uishare string layer, STRBASE)
    FILE_UI=0x710,       # consumer-owned RCD selection page state
    HDR_COPY_CALLS=0x714, HDR_COPY_HITS=0x718,
    HDR_COPY_SRC=0x71C, HDR_COPY_DST=0x720, HDR_COPY_BYTES=0x724,
    HDR_COPY_WHY=0x728, HDR_COPY_FRAME=0x72C,
    BULK_HITS=0x730, BULK_LAST=0x734,
    M12_LEGACY_HITS=0x738, M12_LEGACY_PID=0x73C,
    BIT_UI=0x740,        # bit-depth CSV copies installed, independent of virtual FPS UI
    BIT_EN_AT=0x744,     # two CSV variants x three native bit depths: enabled field
    BIT_EN_ON=0x75C,     # the corresponding original Enabled/Enabled2 values
    LV_RECORDS=0x774,   # resident LV text record substitutions (16 bounded entries), or 0
    LV_MIN=0x778, LV_MAX=0x77C,  # quick rejection outside the LV resource interval
    # (0x780..0x7CF: free -- the former K-row EN arrays)
    VTV_CALLS=0x7D0,     # the shutter-range / angle sites asked
    VTV_HITS=0x7D4,      # ... and got the virtual rate's answer
    VR_EN_AT=0x800,      # 6 CSV copies x 13 rows (9 stock + K): where each row's "a,b" is (absolute)
    VR_EN_ON=0x940,      # ... and its stock "a,b" in that variant
    VRC=0x7DC,           # optional Virtual RCD service, owned tail state
    LV_LABEL=0xA80,      # 14 integer + 14 fractional labels, then literal FPS
    BODY=0xB00,          # rows, entries, lists, overrides, vms follow (filled at entry)
)
S_WORDS_INIT = {'FMTLATCH': 0xFFFFFFFF, 'PICKOK': 1}

# ---- a row (one format) -------------------------------------------------------
ROW = dict(ENUM=0x00, PID=0x04, ASPECT=0x08, ON=0x0C, AW=0x10, AH=0x14,
           REC=0x18, PB=0x1C, ENT0=0x20, NENT=0x24, PREV_H=0x28, BASE=0x2C,
           LABEL=0x30,
           STOCK=0x38,       # §12: the stock resolution value this format records under (2 FHD / 3 UHD)
           MROW=0x3C,        # the menu row (CSV slot) uia_apply handed it this boot, 0 = none
           QSID=0x40,        # three string ids: its QS, SET and FONT images (uia_apply STRBASE)
           PACK=0x4C, PACKLEN=0x50,   # its private NBR pack, in the files' area (absolute)
           PACKCTX=0x54, PACKST=0x58, # the resource context it was registered in; 0 new 1 ok 2 busy 3 failed
           UIRES=0x5C,       # uia_apply's result + 1 (0 = not tried)
           SBY=0x60, NSBY=0x64,   # standby groups (S offset, count): live-view canvases while live
           RFLAGS=0x68,      # the data file's flags: bit 0 clamp, 1 magnifier MAG8 at 4x, 2 Crop Mode supported
           MAXRATE=0x6C,     # the fastest frame rate (the firmware's rate enum), 0 = no limit of ours
           BITMASK=0x70,    # RCD's declared 8/10/12-bit mask; 0 = legacy/native policy
           SIZE=0x74)
# §12/§14: the BIN settings area, file (and block) +32, CFG_BYTES long.  The
# record names formats by LABEL, never by row or value.  Version 1:
CFG = dict(MAGIC=0x00, VERSION=0x04, FLAGS=0x08, SEL=0x0C,   # SEL: 8-byte label, 0 = stock
           SEL_STOCK=0x14, NEN=0x18, EN=0x1C,              # EN: up to 6 enabled labels (§14, the
           SUM=0x4C, BYTES=0x60)                            # consumer settings); NEN 0 = default
CFG_MAGIC, CFG_VERSION = 0x31534352, 1                      # "RCS1"
MAX_ROWS = 6
MAX_VMS = 16                  # S.VMDONOR; mode ids VMID0 .. VMID0 + 15
MAX_AVAIL = 16
QS_SLOTS, QS_CAP = 4, 1024        # record copy buffers: nesting depth, bytes (rcd.qs_max_record() = 778)
S_BYTES = 0xC000             # S, header and body: the shims' window holds the header
OVR_BYTES = 12
T_ZOOM_KIND = 8               # override kind of the magnifier row (7 = the +0x10 value)
# ---- a picker entry: the firmware reads +0..+0xF -------------------------------
ENT = dict(FIVE=0x00, PID=0x04, MODE=0x08, KEYPTR=0x0C, ROW=0x10, KEY=0x14,
           W0=0x24, W1=0x28, ENGFPS=0x2C, NOMINAL=0x30, VM=0x34, VAR=0x38,
           VRATE=0x3C,       # 0, or the virtual rate this entry is for (picked only while S.VRATE == it)
           SIZE=0x40)
# a variant: one virtual profile -- a row's default, or an entry's own canvas / base profile
VAR = dict(PID=0x00, BASE=0x04, ROW=0x08, LIST=0x0C, SIZE=0x10)   # LIST: S offset, 0 = none
# A standby group (S body): {npids, npairs, pids..., pairs...}; while a row is live, a
# canvas whose profile is one of the pids gets the pairs (the old "preview heights" are one)
MAX_VARS, MAX_SBY_GROUPS, MAX_SBY_PIDS, MAX_SBY_PAIRS = 32, 4, 16, 32
PREV_GROUP_PIDS = (5, 210, 227, 257, 258, 259)     # v1 files: prev_h becomes this group
# the virtual profile ids: empty mapping slots in FUN_c043a1c8's class 0 (41..100), rows first
VPID_POOL = [74, 75, 76, 77, 78, 79, 47, 48, 49, 50, 52, 54, 55, 56, 57, 58, 59, 60, 62, 64,
             65, 66, 67, 68, 69, 70, 72, 80, 87, 88, 89, 90]
# ---- a virtual mode -----------------------------------------------------------
# Seven per-mode tables (design §3.2.1): kind, descriptor field (base, count), stride.
TABLES = [('TIM', 0x00, 0x04, 0x20), ('META', 0x08, 0x0C, 100), ('R28', 0x24, 0x28, 0x28),
          ('R38', 0x40, 0x44, 0x38), ('R14', 0x48, 0x4C, 0x14), ('R68', 0xF4, 0xF8, 0x68),
          ('REG', 0x00, 0x04, 0x288)]          # REG: the register descriptor (0xC0B5FDA4)
VM = dict(ID=0x00, DONOR=0x04, FILLED=0x08, REGFILLED=0x0C, ZFILLED=0x10,
          TW0=0x14, TW1=0x18, NOM=0x1C,      # the last picker hit's timing / nominal fps
          PTR=0x20,                          # 7 row pointers (absolute, set when filled)
          CLAMP=0x3C,                        # row data: 1 = turn the video clamp on
          R10=0x40, R10OK=0x44,              # the +0x10 attribute (FUN_c031ffa0), cloned
          OVR=0x48, NOVR=0x4C,               # the data file's overrides {kind, off, value}: S offset, count
          BUF=0x60)
# The eighth per-mode table (2026-10-07, the camera's garbled OG3K take):
# descriptor +0x10 is {value, mode} pairs, 8 bytes, the mode at +4, scanned by
# FUN_c031ffa0, which returns the VALUE (FUN_c0320008 programs the readout with
# it).  Not an index lookup: the layer returns the donor's value.
R10 = (0x10, 0x14, 8)
ZOOM = (0x128, 0x12C, 0x5C)          # the magnifier table: descriptor field, count, stride
BUF_SLACK = 32                      # a row may move inside its buffer to match the base's alignment
_off = VM['BUF']
VM_BUF = {}
for name, _, _, stride in TABLES:
    VM_BUF[name] = _off
    _off += (stride + BUF_SLACK + 7) & ~7
VM_BUF['ZOOM'] = _off
_off += ZOOM[2]
VM['SIZE'] = (_off + 63) & ~63

# ---- §14: a format's data file, \\fpSup\\RESCUS\\<LABEL>.RCD (all little-endian) ----
RCD_MAGIC, RCD_VERSION, RCD_HDR = 0x31444352, 3, 64      # "RCD1" layout, version 3 (modes + fastest rate)
RCD = dict(MAGIC=0x00, VERSION=0x04, HLEN=0x08, FLEN=0x0C, SUM=0x10,   # SUM: FNV-1a of +0x40..end
           NSEC=0x14, SECOFF=0x18, STOCK=0x1C, ASPECT=0x20, FLAGS=0x24,  # FLAGS bit 0: video clamp
           PROFILE=0x28, MINCORE=0x2C, LABEL=0x30, ENUM=0x38,
           MAXRATE=0x3C)          # v3: the fastest rate of all its modes, fps x 100 (= max of MODES)
RCD_SEC_BYTES = 16                      # {type, offset, length, flags (bit 0: required)}
SEC_ENTRIES, SEC_VMODES, SEC_CANVAS, SEC_UI, SEC_PACK = 1, 2, 3, 4, 5
SEC_STANDBY, SEC_ENTCANVAS = 7, 8       # v2 (6 stays reserved for ZOOM); 1 and 8: v2 only
SEC_MODES, SEC_RATECANVAS = 9, 10       # v3: the modes; canvas pairs per rate (and Crop Mode)
SEC_BINFILT = 11                       # {h taps, v taps, h kernel, v kernel, soft/std}
SEC_CAPTURE_TIMING = 12                 # required: per-carrier {rank, crop, w0, w1, engine, nominal}
SEC_BITDEPTH = 13                       # required u32 mask: bit 0 = 8, 1 = 10, 2 = 12
BIT_DEPTHS = (8, 10, 12)                 # native menu order, not a storage policy
RCD_VERSIONS = (3,)                     # what this core reads (v1/v2 carried per-rate entries)
RCD_MODE_BYTES = 20                     # donor, fastest rate (fps x 100), hmax, PAL hmax (0 = hmax), x
RCD_MAX_MODES = 4
RCD_MAX_RCANVAS = 8                     # {rank (0 = every rate), crop (0/1), base profile, n, pairs}
RCD_ENT_BYTES = 40                      # key[16], donor, w0, w1, engfps, nominal, 0
RCD_OVR_BYTES = 16                      # donor, kind, offset, value
RCD_CANVAS_HEAD = 32                    # prev_h, act w, act h, n_rec, n_pb, 0, 0, 0; then pairs
RCD_UI_ROW, RCD_UI_SUM = 32, 16         # the Settings row text, the summary text (NUL-padded)
RCD_UI_BYTES = RCD_UI_ROW + RCD_UI_SUM
RCD_MAX_FILE = 0x20000
RCD_MAX_ENT, RCD_MAX_OVR, RCD_MAX_PAIRS, RCD_MAX_SECS = 32, 256, 64, 16
RCD_MAX_NAMES = 16                      # .RCD names looked at (sorted); more are not read
CORE_VERSION = 4                        # v4 supports RCD-owned bit-depth availability
# why a file was refused (S.RCD_WHY low half)
RCD_WHY = dict(OPEN=1, SIZE=2, ROOM=3, READ=4, MAGIC=5, VERSION=6, NEWER=7, SUM=8, SECTION=9,
               UNKNOWN=10, FIELD=11, ENTRY=12, CANVAS=13, UI=14, PACK=15, OVERRIDE=16,
               DUPLICATE=17, PROFILE=18, S_FULL=19, VMS=20, DISABLED=21, EXCESS=22, STANDBY=23,
               BINFILT=24, BITDEPTH=25)

# ---- firmware -----------------------------------------------------------------
IMAGER = 0xC343B588           # XC_ImageSensorIMX410 (its +0 is the mode descriptor)
REGDESC = 0xC0B5FDA4          # FUN_c0326e20: {register-record base, count}
MAPPING = 0xC0BD05D4
PREV_PROFILES = (5, 210, 227, 257, 258, 259)
CLAMP = ((0x04, 0x00000008), (0x18, 0x0000C000))   # the video clamp bits in the R38 row
ENUM_RES_BASE = 0x4D4E4500    # uishare ui/enums.py UIS_RES_ENUM_BASE
VPID0, VMID0 = 74, 230        # empty mapping slots 74..79 (class 0, like p83/p13); free mode ids 230..245

# ---- C entry points (S.FN + 4*i) and hook slots (S.NEXT + 4*i) ----------------
FNS = ['PICK', 'SEL', 'FMT', 'CANVAS', 'NAME', 'OUT', 'VLOOK', 'V32', 'AC38', 'FPS', 'CMT', 'SAVE',
       'QSREC', 'QSLAY', 'QSLOAD', 'GATE', 'RCMT', 'VTV', 'VGUI', 'BINPATH', 'BINKERNEL', 'RECRATE', 'HDRCOPY', 'BULK', 'BIT']
HOOKS = [  # name, site, kind, replay ('' = BL site through its own target / none)
    # Inner copy entry: leave Gyro2's outer C038C77C chain intact.
    ('hdrcopy', 0xC00FBB90, 'tw'),
    # The writer's local setup descriptor, before native FS configuration.
    ('bulk', 0xC03A5144, 'bl'),
    ('picker', 0xC043CCF8, 'b'), ('setter', 0xC005C020, 'b'), ('fmtset', 0xC005BE58, 'b'),
    ('canvas', 0xC043A19C, 'bl'), ('vpro', 0xC043A18C, 'bl'), ('name', 0xC0437B48, 'b'),
    ('aspect', 0xC0306EA0, 'b'), ('aspect2', 0xC0306EEC, 'b'), ('out', 0xC0437E98, 'b'),
    ('gs', 0xC03A6DD8, 'b'),
    ('lk_tim', 0xC0320BA0, 'b'), ('lk_meta', 0xC0320B38, 'b'), ('lk_r28', 0xC0320E90, 'b'),
    ('lk_r38', 0xC0320F60, 'b'), ('lk_r14', 0xC0320EF8, 'b'), ('lk_r68', 0xC0320C00, 'b'),
    ('lk_reg', 0xC0326DB8, 'b'), ('lk_r10', 0xC031FFA0, 'b'),
    # the shutter-angle nominal fps (og3kfps's four call sites, as today's core)
    ('fps1', 0xC02092CC, 'bl'), ('fps2', 0xC0218AEC, 'bl'), ('fps3', 0xC0219260, 'bl'),
    ('fps4', 0xC03AA568, 'bl'),
    # §12: the menu's two MV_Resolution commit callbacks (Settings FUN_c057a6a0,
    # Quick Set FUN_c05824d0; [r0+8] = the committed row) and the power-off
    # settings save's call site (C0088C60 `bl FUN_c0088660`, raw-view's point)
    ('cmt_set', 0xC057A6A0, 'b'), ('cmt_qs', 0xC05824D0, 'b'), ('save', 0xC0088C60, 'bl'),
    # the magnifier's per-mode table (descriptor +0x128, stride 0x5C) is scanned
    # inline, no index function (design §3.2.1a): the row copier FUN_c031ac38
    # gets our row, FUN_c031acd8 and the one `bl c03212f8` in FUN_c031b3a0 whose
    # result feeds an inline scan see the donor, v32 computes from our row.
    ('ac38', 0xC031AC38, 'b'), ('acd8', 0xC031ACD8, 'b'), ('zg', 0xC031B660, 'bl'),
    ('v32', 0xC03249A0, 'b'),
    # §13: the Quick Set layers (Thumb sites, a B.W to a Thumb veneer that enters
    # an ARM shim): one NBU record, one layout load, one NBR pack load
    ('qsrec', 0xC05E6400, 'tw'), ('qslay', 0xC05D90F0, 'tw'), ('qsload', 0xC05E84D8, 'tw'),
    # Crop Mode and frame-rate greying (2026-10-07; Jose's sites, our logic): Crop Mode's
    # availability FUN_c04a1788, its effective value (MenuItemCropMode::v8 tail), the
    # frame rate's normalising limit (MenuItemMovieFrameRate::v8 join), the frame-rate
    # list's state class (FUN_c04a1120 join), the magnifier key's MAG4 (FUN_c043b638)
    ('cropst', 0xC04A1788, 'b'), ('cropeff', 0xC00A93BC, 'b'), ('frmax', 0xC00A87E4, 'b'),
    ('frclass', 0xC04A121C, 'b'), ('mag', 0xC043B6A4, 'b'),
    # the virtual frame rate: the two MV_FrameRate commit callbacks (Settings
    # FUN_c057a6f8 is QS-side per res-lab's camera notes, FUN_c05821b8 the
    # Settings menu; [r0+8] = the committed row) -- row nine = 239.76
    ('rcmt1', 0xC057A6F8, 'b'), ('rcmt2', 0xC05821B8, 'b'),
    # the virtual rate's shutter range and angle list (2026-10-08 RE, design §15):
    # the slowest-Tv base value's per-fps join (MenuItemFactory vptr+0x4A0 FUN_c007f2b0,
    # `bl c0085ac0` with r1 -> {num, den}) and its GUI copy (FUN_c0553ab8, the
    # slowest-limit list), the shutter's display clamp (MenuItemShutterSpeed::v3,
    # fp = the rate enum, [sp+0x28] = {num, den}), the maximum-angle list's rate
    # (FUN_c0554758 `bl FUN_c005c0f0`: an unknown enum throws -- 0 = 15p, every angle),
    # and the angle-to-Tv table's fps x 100 (FUN_c052dca8, r6, [sp] = the enum)
    ('tvmin', 0xC007F5B4, 'bl'), ('tvmin2', 0xC0553CDC, 'bl'), ('tvdisp', 0xC00A075C, 'b'),
    ('anglist', 0xC0554768, 'bl'), ('angtv', 0xC052DCFC, 'b'),
    # The stock aspect getter only accepts 1..8. Aspect 9 is 2:1, used by
    # Julien's configurator: answer it only for our live/picked or playback row.
    ('ratio', 0xC02DAFA0, 'b'),
    ('vrcgui', 0xC056461C, 'bl'),
    ('binpath', 0xC0325228, 'b'),
    ('binkernel1', 0xC032DDF0, 'bl'), ('binkernel2', 0xC032DE70, 'bl'),
    # CinemaDNG FrameRate rational; the native setting remains a supported carrier.
    ('recrate', 0xC00C9BD0, 'b'),
    ('bitclass', 0xC04A13E4, 'b'),        # native quality exclusion provider's result
    ('bitnorm', 0xC00A7FFC, 'b'),         # native quality normalizer's result
]
RFLAG_CLAMP, RFLAG_MAG8, RFLAG_CROP = 1, 2, 4
# the virtual frame rates, core-defined (rcd entries only say which ones they time):
# rank (fps x 100), the stock internal it rides on, that rate's export (summary)
VRATES = ((23976, 7, 10), (27972, 7, 10), (1798, 1, 1), (899, 1, 1))
VR_K, VR_ROW0, VR_CSVS = 4, 9, 6
VR_ROWS = VR_ROW0 + VR_K     # the frame-rate list's rows the core greys: the stock nine + K
# the slowest shutter each allows, 1/n s (the firmware's own convention: 119.88 -> 1/120)
VR_TV = tuple((r + 50) // 100 for r, _, _ in VRATES)
CFG_FLAG_VRATE = 1     # the BIN record: FLAGS bit 0 + (rank << 8) of the virtual rate chosen
RATE_ENUMS = (0, 1, 12, 2, 3, 13, 4, 5, 6, 7)     # the firmware's table at 0xC0735F60
RATE_RANKS = {0: 1500, 1: 2398, 12: 2400, 2: 2500, 3: 2997, 13: 4800, 4: 5000, 5: 5994, 6: 10000, 7: 11988}
RATE_TABLE = 0xC0735F60
RATE_SUFFIX = {'23_98': 1, '24': 12, '25': 2, '30': 3, '48': 13, '50': 4, '60': 5, '100': 6, '120': 7}
SBY_COND = {'always': 0, 'crop_off': 1, 'crop_on': 2}   # a standby group's npids high half

# ---- the core's timing (2026-10-08, user: a format is its modes + their fastest rate) ----
# Every rate: its frame period in 72 MHz cycles (broadcast rates are rational, so exact),
# whether it is a PAL rate (a mode's PAL hmax), the canvas +0x30 the stock firmware
# declares on that rate's slot (ISP cadence; 100 -> 50.0, 119.88 -> 60.0 as stock),
# the nominal fps (shutter angle). DNG FrameRate is a separate recording-setting
# lookup at C00C9BD0, not this canvas field. Keep the pre-experiment v38
# virtual cadence here. The engine60/native30/engine30 trials were withdrawn
# after the user reported a 120p preview regression; they are not accepted fixes.
CLOCK = 72_000_000
MIN_TAIL = 270            # the shortest tail proven on the camera (OG3K100, mode 117)


def _f32(x):
    return struct.unpack('<I', struct.pack('<f', x))[0]


#        row, suffix, enum, cycles, pal, +0x30, nominal, rank
RATES = ((0, '23_98', 1, 3003000, 0, 24.0, 24, 2398), (1, '24', 12, 3000000, 0, 24.0, 24, 2400),
         (2, '25', 2, 2880000, 1, 25.0, 25, 2500), (3, '30', 3, 2402400, 0, 30.0, 30, 2997),
         (4, '48', 13, 1500000, 0, 48.0, 48, 4800), (5, '50', 4, 1440000, 1, 50.0, 50, 5000),
         (6, '60', 5, 1201200, 0, 60.0, 60, 5994), (7, '100', 6, 720000, 1, 50.0, 100, 10000),
         (8, '120', 7, 600600, 0, 60.0, 120, 11988))
#        cycles, +0x30 (engine cadence), nominal, the stock row it rides on, generated
VR_TIME = ((300300, 240000 / 1001, 240, 8, 1), (257400, 280000 / 1001, 280, 8, 1),
           (4004000, 18000 / 1001, 18, 0, 1),
           (8008000, 9000 / 1001, 9, 0, 0))     # 8.99: not until the camera says it can (user)


ALL_RANKS = tuple(r[7] for r in RATES) + (23976, 27972, 1798, 899)
MAX_GEN = 2 * (len(RATES) + 4)          # entries a row can make (each rate, plain and CROP)


def solve(hm, cycles):
    """(vmax, tail) for a frame of `cycles`: the sensor's real period is hmax x vmax
    (FLAG_AND_PICKER_DISAGREE.md §36, measured) -> vmax rounded; tail keeps the
    firmware's own count hmax x (vmax - 1) + tail exact, never below MIN_TAIL."""
    vm = (2 * cycles + hm) // (2 * hm)
    tail = cycles - hm * (vm - 1)
    if tail < MIN_TAIL:
        vm, tail = vm - 1, tail + hm
    if vm < 2 or vm > 0xFFFF or tail > 0xFFFF:
        return None
    return vm, tail


def gen_entries(label, modes, flags):
    """The picker entries the core makes for a format (ogc.c gen_entry, same order):
    each stock rate then each generated virtual rate, the first mode fast enough, the
    plain key then (Crop Mode formats) its CROP twin.  modes: [(donor, maxrate, hmax,
    pal_hmax, x)]."""
    out = []
    cand = [(suf, cyc, pal, eng, nom, rank, 0) for _, suf, _, cyc, pal, eng, nom, rank in RATES]
    for k, (cyc, eng, nom, base, on) in enumerate(VR_TIME):
        if on:
            cand.append((RATES[base][1], cyc, 0, eng, nom, VRATES[k][0], VRATES[k][0]))
    for suf, cyc, pal, eng, nom, rank, vr in cand:
        m = next((m for m in modes if rank <= m[1]), None)
        if m is None:
            continue
        hm = m[3] if pal and m[3] else m[2]
        t = solve(hm, cyc)
        if t is None:
            continue
        for crop in ((0, 1) if flags & RFLAG_CROP else (0,)):
            out.append({'key': label + suf + ('CROP' if crop else ''), 'donor': m[0],
                        'w0': hm | t[1] << 16, 'w1': t[0] | m[4] << 16, 'engfps': _f32(eng),
                        'nominal': nom, 'vrate': vr, 'rank': rank, 'crop': crop})
    return out
HOOK_INDEX = {n: i for i, (n, _, _) in enumerate(HOOKS)}
LOOKUPS = ['lk_tim', 'lk_meta', 'lk_r28', 'lk_r38', 'lk_r14', 'lk_r68', 'lk_reg', 'lk_r10']


def header():
    out = ['/* generated by ogc_layout.py -- do not edit */', '#ifndef OGC_LAYOUT_H',
           '#define OGC_LAYOUT_H']
    d = {'OGC_LAYOUT0': LAYOUT0, 'OGC_S_COORD': S_COORD, 'OGC_MAGIC': MAGIC,
         'OGC_VERSION': VERSION, 'OGC_IMAGER': IMAGER, 'OGC_REGDESC': REGDESC,
         'OGC_MAPPING': MAPPING, 'OGC_ENUM_RES_BASE': ENUM_RES_BASE,
         'OGC_CFG_MAGIC': CFG_MAGIC, 'OGC_CFG_VERSION': CFG_VERSION, 'OGC_MAX_ROWS': MAX_ROWS,
         'OGC_VM_SIZE': VM['SIZE'], 'OGC_BUF_SLACK': BUF_SLACK, 'OGC_NTABLES': len(TABLES),
         'Z_FIELD': ZOOM[0], 'Z_COUNT': ZOOM[1], 'Z_STRIDE': ZOOM[2], 'VM_BUF_ZOOM': VM_BUF['ZOOM'],
         'R10_FIELD': R10[0], 'R10_COUNT': R10[1], 'R10_STRIDE': R10[2], 'T_R10': len(TABLES),
         'T_ZOOM': T_ZOOM_KIND, 'OGC_MAX_VMS': MAX_VMS, 'OGC_MAX_AVAIL': MAX_AVAIL,
         **({'OGC_CAP_BACK': CAP_BACK} if HOOKCNT else {}),
         'OGC_S_BYTES': S_BYTES, 'OVR_BYTES': OVR_BYTES, 'OGC_VPID0': VPID0,
         'OGC_QS_SLOTS': QS_SLOTS, 'OGC_QS_CAP': QS_CAP, 'OGC_MAX_VARS': MAX_VARS,
         'RFLAG_CLAMP': RFLAG_CLAMP, 'VR_K': VR_K, 'VR_ROWS': VR_ROWS, 'VR_ROW0': VR_ROW0, 'VR_CSVS': VR_CSVS,
         **{f'VR_RANK{i}': r for i, (r, _, _) in enumerate(VRATES)},
         **{f'VR_BASE{i}': b for i, (_, b, _) in enumerate(VRATES)},
         **{f'VR_EXPORT{i}': e for i, (_, _, e) in enumerate(VRATES)},
         **{f'VR_TV{i}': t for i, t in enumerate(VR_TV)},
         'CFG_FLAG_VRATE': CFG_FLAG_VRATE, 'RATE_TABLE': RATE_TABLE, 'RFLAG_MAG8': RFLAG_MAG8, 'RFLAG_CROP': RFLAG_CROP,
         **{f'PREV_PID{i}': v for i, v in enumerate(PREV_GROUP_PIDS)},
         'OGC_MAX_SBY_GROUPS': MAX_SBY_GROUPS, 'OGC_MAX_SBY_PIDS': MAX_SBY_PIDS,
         'OGC_MAX_SBY_PAIRS': MAX_SBY_PAIRS, 'SEC_STANDBY': SEC_STANDBY,
         'SEC_ENTCANVAS': SEC_ENTCANVAS, 'RCD_VERSION_MIN': RCD_VERSIONS[0],
         'RCD_VERSION_MAX': RCD_VERSIONS[-1],
         'SEC_MODES': SEC_MODES, 'SEC_RATECANVAS': SEC_RATECANVAS, 'SEC_BINFILT': SEC_BINFILT,
         'SEC_CAPTURE_TIMING': SEC_CAPTURE_TIMING,
         'SEC_BITDEPTH': SEC_BITDEPTH,
         'RCD_MODE_BYTES': RCD_MODE_BYTES,
         'RCD_MAX_MODES': RCD_MAX_MODES, 'MAX_GEN': MAX_GEN, 'NRATES': len(RATES), 'RCD_MAX_RCANVAS': RCD_MAX_RCANVAS, 'MIN_TAIL': MIN_TAIL,
         **{f'RATE_CYC{j}': r[3] for j, r in enumerate(RATES)},
         **{f'RATE_PAL{j}': r[4] for j, r in enumerate(RATES)},
         **{f'RATE_ENG{j}': _f32(r[5]) for j, r in enumerate(RATES)},
         **{f'RATE_NOM{j}': r[6] for j, r in enumerate(RATES)},
         **{f'RATE_RANK{j}': r[7] for j, r in enumerate(RATES)},
         **{f'VR_CYC{k}': v[0] for k, v in enumerate(VR_TIME)},
         **{f'VR_ENG{k}': _f32(v[1]) for k, v in enumerate(VR_TIME)},
         **{f'VR_NOM{k}': v[2] for k, v in enumerate(VR_TIME)},
         **{f'VR_BASEJ{k}': v[3] for k, v in enumerate(VR_TIME)},
         **{f'VR_GEN{k}': v[4] for k, v in enumerate(VR_TIME)},
         'RCD_MAGIC': RCD_MAGIC, 'RCD_VERSION': RCD_VERSION, 'RCD_HDR': RCD_HDR,
         'RCD_SEC_BYTES': RCD_SEC_BYTES, 'SEC_ENTRIES': SEC_ENTRIES, 'SEC_VMODES': SEC_VMODES,
         'SEC_CANVAS': SEC_CANVAS, 'SEC_UI': SEC_UI, 'SEC_PACK': SEC_PACK,
         'RCD_ENT_BYTES': RCD_ENT_BYTES, 'RCD_OVR_BYTES': RCD_OVR_BYTES,
         'RCD_CANVAS_HEAD': RCD_CANVAS_HEAD, 'RCD_UI_ROW': RCD_UI_ROW, 'RCD_UI_SUM': RCD_UI_SUM,
         'RCD_UI_BYTES': RCD_UI_BYTES, 'RCD_MAX_FILE': RCD_MAX_FILE, 'RCD_MAX_ENT': RCD_MAX_ENT,
         'RCD_MAX_OVR': RCD_MAX_OVR, 'RCD_MAX_PAIRS': RCD_MAX_PAIRS, 'RCD_MAX_SECS': RCD_MAX_SECS,
         'RCD_MAX_NAMES': RCD_MAX_NAMES, 'OGC_CORE_VERSION': CORE_VERSION}
    d.update({f'S_{k}': v for k, v in S.items()})
    d.update({f'ROW_{k}': v for k, v in ROW.items()})
    d.update({f'CFG_{k}': v for k, v in CFG.items()})
    d.update({f'ENT_{k}': v for k, v in ENT.items()})
    d.update({f'VAR_{k}': v for k, v in VAR.items()})
    d.update({f'VM_{k}': v for k, v in VM.items()})
    d.update({f'RH_{k}': v for k, v in RCD.items()})
    d.update({f'WHY_{k}': v for k, v in RCD_WHY.items()})
    for i, (name, field, count, stride) in enumerate(TABLES):
        d[f'T_{name}'] = i
        d[f'T_{name}_FIELD'] = field
        d[f'T_{name}_COUNT'] = count
        d[f'T_{name}_STRIDE'] = stride
        d[f'VM_BUF_{name}'] = VM_BUF[name]
    for i, n in enumerate(FNS):
        d[f'FN_{n}'] = S['FN'] + 4 * i
    for n, i in HOOK_INDEX.items():
        d[f'NX_{n.upper()}'] = S['NEXT'] + 4 * i
    for k, v in d.items():
        out.append(f'#define {k} 0x{v:X}')
    out.append('#endif')
    return '\n'.join(out) + '\n'


def s_header():
    """The S header as the file carries it (S_COORD, BODY bytes): only the words
    that are not filled at run time.  The entry fills the rest from the data files."""
    buf = bytearray(S['BODY'])

    def put(off, v):
        struct.pack_into('<I', buf, off, v & 0xFFFFFFFF)

    put(S['MAGIC'], MAGIC)
    put(S['VERSION'], VERSION)
    for k, v in S_WORDS_INIT.items():
        put(S[k], v)
    put(S['VPID0'], VPID0)
    put(S['VMID0'], VMID0)
    for i, pid in enumerate(VPID_POOL):
        put(S['POOL'] + 4 * i, pid)
    return bytes(buf)


def standby_groups(row):
    """The row's standby groups as the core builds them: the preview heights first
    (a 3:2 row's prev_h, on the six preview profiles), then the file's own."""
    out = []
    if row['aspect'] == 2 and row.get('prev_h'):
        out.append((list(PREV_GROUP_PIDS), [(0x28, row['prev_h'])]))
    out += [(list(g[0]), list(g[1]), g[2] if len(g) > 2 else 0) for g in row.get('standby', [])]
    return out


# the words of a filled S that the entry writes from run-time facts (addresses,
# what uia_apply handed out); a reference comparison masks them
RUNTIME_ROW = ('ON', 'MROW', 'QSID', 'PACK', 'PACKLEN', 'PACKCTX', 'PACKST', 'UIRES')


def state_blob(rows):
    """The reference for what the entry builds in S from the data files (§14.3):
    `rows` are rcd.decode() dicts (with 'base_row'), enabled and in order.
    Returns (S bytes up to S_END, facts).  Run-time words (RUNTIME_ROW, the
    entries' key pointers, the run-time header words) are left 0."""
    buf = bytearray(s_header())

    def put(off, v):
        struct.pack_into('<I', buf, off, v & 0xFFFFFFFF)

    vms = []
    for r, row in enumerate(rows):
        for e in row['entries']:
            if (r, e['donor']) not in vms:
                vms.append((r, e['donor']))
    if len(rows) > MAX_ROWS or len(vms) > MAX_VMS:
        raise ValueError('too many rows or virtual modes')
    for r, row in enumerate(rows):
        put(S['BASEROW'] + 4 * r, row['base_row'])
    for v, (_, donor) in enumerate(vms):
        put(S['VMDONOR'] + 4 * v, donor)

    rows_off = len(buf)
    buf += bytes(ROW['SIZE'] * len(rows))
    ents = [(r, e) for r, row in enumerate(rows) for e in row['entries']]
    ents_off = len(buf)
    buf += bytes(ENT['SIZE'] * len(ents))
    # variants: each row's default (its pid, its base row), then each entry's own
    var = [(r, row['base_row'], None) for r, row in enumerate(rows)]
    sel = {}                    # (row, selector index) -> variant
    for r, row in enumerate(rows):
        for i, rc in enumerate(row.get('rate_canvas', [])):
            sel[(r, i)] = len(var)
            var.append((r, rc['base_row'], rc['pairs']))

    def var_of(r, e):
        """an entry's variant: the first of its row's selectors that names its rate
        (or every rate) and its Crop Mode, else the row's default"""
        for i, rc in enumerate(rows[r].get('rate_canvas', [])):
            if rc['rank'] in (0, e['rank']) and rc['crop'] == e['crop']:
                return sel[(r, i)]
        return r
    if len(var) > MAX_VARS:
        raise ValueError('too many variants')
    vars_off = len(buf)
    buf += bytes(VAR['SIZE'] * len(var))
    lists = {}
    for r, row in enumerate(rows):
        for kind in ('canvas_rec', 'canvas_pb'):
            lists[(r, kind)] = len(buf)
            for off, val in row[kind]:
                buf += struct.pack('<2I', off, val)
            buf += struct.pack('<I', 0xFFFFFFFF)
    var_list = {}
    for v, (_, _, pairs) in enumerate(var):
        if pairs is None:
            continue
        var_list[v] = len(buf)
        for off, val in pairs:
            buf += struct.pack('<2I', off, val)
        buf += struct.pack('<I', 0xFFFFFFFF)
    sby = {}
    for r, row in enumerate(rows):
        groups = standby_groups(row)
        sby[r] = (len(buf) if groups else 0, len(groups))
        for g in groups:
            pids, pairs = g[0], g[1]
            cond = g[2] if len(g) > 2 else 0
            buf += struct.pack('<2I', cond << 16 | len(pids), len(pairs))
            buf += struct.pack(f'<{len(pids)}I', *pids)
            for off, val in pairs:
                buf += struct.pack('<2I', off, val)
    ovr = {}
    for v, (r, donor) in enumerate(vms):
        mine = [o for o in rows[r].get('overrides', []) if o[0] == donor]
        ovr[v] = (len(buf) if mine else 0, len(mine))
        for _, kind, off, val in mine:
            buf += struct.pack('<3I', kind, off, val)
    while len(buf) % 64:
        buf += b'\0'
    vms_off = len(buf)
    buf += bytes(VM['SIZE'] * len(vms))
    for v, (r, base, _) in enumerate(var):
        b = vars_off + VAR['SIZE'] * v
        put(b + VAR['PID'], VPID_POOL[v])
        put(b + VAR['BASE'], base)
        put(b + VAR['ROW'], r)
        put(b + VAR['LIST'], var_list.get(v, 0))
    put(S['NVAR'], len(var))
    put(S['VARS'], vars_off)

    n0 = 0
    for r, row in enumerate(rows):
        b = rows_off + ROW['SIZE'] * r
        aspect = row['aspect']
        put(b + ROW['ENUM'], row['enum'])
        put(b + ROW['PID'], VPID_POOL[r])
        put(b + ROW['ASPECT'], aspect)
        put(b + ROW['AW'], row['act'][0])
        put(b + ROW['AH'], row['act'][1])
        put(b + ROW['REC'], lists[(r, 'canvas_rec')])
        put(b + ROW['PB'], lists[(r, 'canvas_pb')])
        put(b + ROW['ENT0'], n0)
        put(b + ROW['NENT'], len(row['entries']))
        put(b + ROW['PREV_H'], row['prev_h'] if aspect == 2 else 0)
        put(b + ROW['BASE'], row['base_row'])
        put(b + ROW['STOCK'], row['stock_value'])
        put(b + ROW['RFLAGS'], row.get('flags', 1 if row.get('clamp') else 0))
        put(b + ROW['MAXRATE'], row.get('maxrate', 0))
        put(b + ROW['BITMASK'], sum(1 << BIT_DEPTHS.index(d) for d in row.get('bit_depths', ())))
        put(b + ROW['SBY'], sby[r][0])
        put(b + ROW['NSBY'], sby[r][1])
        lab = row['label'].encode()
        if not 0 < len(lab) < 8:
            raise ValueError('label length')
        buf[b + ROW['LABEL']:b + ROW['LABEL'] + len(lab)] = lab
        n0 += len(row['entries'])
    for i, (r, e) in enumerate(ents):
        b = ents_off + ENT['SIZE'] * i
        vr = var_of(r, e)
        put(b + ENT['FIVE'], 5)
        put(b + ENT['PID'], VPID_POOL[vr])
        put(b + ENT['VAR'], vr)
        put(b + ENT['VRATE'], e.get('vrate', 0))
        v = vms.index((r, e['donor']))
        put(b + ENT['MODE'], VMID0 + v)
        put(b + ENT['ROW'], r)
        key = e['key'].encode()
        if not 0 < len(key) < 16:
            raise ValueError('key length')
        buf[b + ENT['KEY']:b + ENT['KEY'] + len(key)] = key
        put(b + ENT['W0'], e['w0'])
        put(b + ENT['W1'], e['w1'])
        put(b + ENT['ENGFPS'], e['engfps'])
        put(b + ENT['NOMINAL'], e['nominal'])
        put(b + ENT['VM'], v)
    for v, (r, donor) in enumerate(vms):
        b = vms_off + VM['SIZE'] * v
        put(b + VM['ID'], VMID0 + v)
        put(b + VM['DONOR'], donor)
        put(b + VM['CLAMP'], 1 if rows[r].get('clamp') else 0)
        put(b + VM['OVR'], ovr[v][0])
        put(b + VM['NOVR'], ovr[v][1])
    put(S['NROWS'], len(rows))
    put(S['ROWS'], rows_off)
    put(S['NENT'], len(ents))
    put(S['ENTS'], ents_off)
    put(S['NVM'], len(vms))
    put(S['VMS'], vms_off)
    put(S['S_END'], len(buf))
    if len(buf) > S_BYTES:
        raise ValueError('S overflows S_BYTES')
    facts = {'rows_off': rows_off, 'ents_off': ents_off, 'vms_off': vms_off, 's_end': len(buf),
             'vms': [{'id': VMID0 + v, 'donor': d, 'row': r} for v, (r, d) in enumerate(vms)],
             'vars': [{'pid': VPID_POOL[v], 'row': r, 'base_row': b, 'pairs': p}
                      for v, (r, b, p) in enumerate(var)],
             'keys': [e['key'] for _, e in ents]}
    return bytes(buf), facts
