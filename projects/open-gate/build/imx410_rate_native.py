"""Native 240 fps menu/setting bridge; immutable tables and CUSTOM-only gates.

Three distinct enum domains must not be confused: row 9, setting enum 8,
export/picker enum 11. Export enum 5 enters a native assert; setting 5 is 59.94.
"""
from pathlib import Path
import struct
from armasm import assemble

B = 0xC0000000
INTERNAL, EXPORT, RANK = 8, 11, 23976
FLAG, FMTLATCH = 0xC0731C08, 0xC0731C20
RANK_TABLE, LEGAL_TABLE = 0xC0730000, 0xC0730088
LEGAL_DESC = 0xC07300D8
INPUT_PAIR, RATE_LIST = 0xC07301C0, 0xC0730220
# ⛔ SETTINGS_AREA_FIRST_RULE (research/SETTINGS_AREA_FIRST_RULE.md): the stock
# frame-rate setting must never hold internal 8 -- it is persisted and read at
# boot before any loader.  Row nine (239.76) therefore hands stock internal 7
# (119.88); "row nine was chosen" lives only in RAM at RATE240, zeroed by the
# loader every boot.  Both MV_FrameRate setter callbacks, FUN_c057a6f8 and
# FUN_c05821b8 (row->value via C06BDAB0, then settings vtable+0x140), set RATE240 and orders the duplicate
# (7,8)/(7,9) pairs so stock's value->row lookup lands on the chosen row.
ROW240_VALUE = 7
RATE240 = 0xC0731C48
SUMMARY_STATE_10 = 0xC0730144    # imx410_plan RATE_PAIR entry export 10 -> state
STOCK_ORDER = (1, 12, 2, 3, 13, 4, 5, 6, 7)
# Only these named sites are altered outside owned cave memory.
MAPPING_SITES = (
 (0xC0063528, 0xE3051F60, 'rank table low'),
 (0xC006352C, 0xE34C1073, 'rank table high'),
 (0xC0063530, 0xE3A0300A, 'rank table count'),
 (0xC06BDB0C, 0xE3002224, 'input pair table low'),
 (0xC06BDB10, 0xE34C22E4, 'input pair table high'),
 (0xC06BDB18, 0xE3A0200A, 'input pair table count'),
)
HOOKS = (
 (0xC04A121C, 0xC0732A20, 0xE1A00001, 'B', 'native rate list class'),
 (0xC00A87E4, 0xC0732AA0, 0xE1A01004, 'B', 'native rate normaliser cap'),
 (0xC049A788, 0xC0732B20, 0xE92D4030, 'B', 'native menu rate list'),
 (0xC05332A8, 0xC0732BA0, 0xE24DD008, 'B', 'native Quick Set rate list'),
 (0xC00A8858, 0xC0732C10, 0xE1A00005, 'B', 'native legal/export cached table'),
 (0xC057A6F8, 0xC0732B20, 0xE92D40F0, 'B', 'MV_FrameRate row-nine RAM flag'),  # reuses ROLE 3's slot (not armed)
 (0xC05821B8, 0xC0732BA0, 0xE92D40F0, 'B', 'MV_FrameRate (2nd setter) row-nine RAM flag'),  # ROLE 4's slot
)
EXTERNAL_SITES = tuple(a for a, _, _ in MAPPING_SITES) + tuple(h[0] for h in HOOKS)
# Stock per-rate switches on the internal enum (`cmp rN,#13` + byte jump table,
# each fed by the frame-rate getter C005C0F0).  Internal 8..11 share the
# default case.  Camera 2026-10-01: selecting 240 froze only once the stock
# setting really held internal 8 (bisection M / M-no-native / M-no-normaliser).
# Source (out/decomp/full):
#   FUN_c058f380  frame-rate value string ID for HELP_FactorValueType0
#                 (GuiExclFunc): default returns NULL -> handed to the GUI.
#   FUN_c0554758  builds a per-rate std::function; default stores an EMPTY one.
#   FUN_c0553ab8, MenuItemFactory_w71c1__v294, MenuItemSutterSpeedSettingMode__v10,
#   and the switch at C058FB00 fall back to a stock default value.
# Alias internal 8 to the 119.88 case (entry 7) in all six so the stock
# pipeline behaves exactly as at 119.88; our recipe owns the sensor at 240.
# (cmp address, stock 14-byte table)
RATE_SWITCHES = (
 (0xC0553BD8, bytes.fromhex('38030e1420262c3238383838081a')),
 (0xC0554780, bytes.fromhex('28030c10181c20242c2c2c2c0814')),
 (0xC058F394, bytes.fromhex('27030b0f171b1f23272727270713')),
 (0xC007F498, bytes.fromhex('0308141a262c32383e3e3e3e0e20')),
 (0xC00A0C20, bytes.fromhex('1603080a0e10121416161616060c')),
 (0xC058FB00, bytes.fromhex('26030a0e161a1e22262626260612')),
)


def switch_patches(img):
    """Word writes making entry INTERNAL of each RATE_SWITCHES table equal entry 7."""
    out = []
    if not WITH_SWITCH_ALIAS:
        return []
    for cmp, stock in RATE_SWITCHES:
        w = struct.unpack_from('<5I', img, cmp - B)
        if w[0] & 0xFFF0FFFF != 0xE350000D or w[1] >> 24 != 0x8A or w[4] & 0xFFFFFFF0 != 0xE08FF100:
            raise ValueError(f'rate switch shape changed at {cmp:#x}')
        table = cmp + 20
        if img[table-B:table-B+14] != stock or len(set(stock[8:12])) != 1 or stock[7] == stock[8]:
            raise ValueError(f'rate switch table changed at {table:#x}')
        at = table + INTERNAL
        word = bytearray(img[(at & ~3)-B:(at & ~3)-B+4])
        word[at & 3] = stock[7]
        out.append((at & ~3, struct.unpack('<I', word)[0], f'rate switch {cmp:#x}: internal 8 -> 119.88 case'))
    return out


# Diagnostic bisection only: hook sites left at their stock word (payload still
# assembled, so ROLE numbering by HOOKS order is unchanged).  Empty in products.
DISARM = set()
# One-row-240: internal 8 never reaches stock, so the menu / QS list hooks that
# only existed to add it are not armed (class hook already yields the full list).
NOT_ARMED = {0xC049A788, 0xC05332A8}
# Retired with the decision to not alter the stock flow (see RATE_SWITCHES).
WITH_SWITCH_ALIAS = False


def _word(img, a):
 return struct.unpack_from('<I', img, a-B)[0]


def _mov(rd, imm, high=False):
 return (0xE3400000 if high else 0xE3000000) | ((imm>>12)&15)<<16 | rd<<12 | (imm&0xfff)


def _b(site, target):
 delta=target-site-8
 if delta%4 or not -(1<<25)<=delta<(1<<25): raise ValueError('branch out of range')
 return 0xEA000000 | ((delta>>2)&0xffffff)


def tables(img):
 rank=img[0xC0735F60-B:0xC0735FD8-B]
 triples=tuple(struct.unpack_from('<III', rank, i*12) for i in range(10))
 expected=((0,0,1500),(1,1,2398),(12,2,2400),(2,3,2500),(3,4,2997),
           (13,6,4800),(4,7,5000),(5,8,5994),(6,9,10000),(7,10,11988))
 if triples != expected: raise ValueError('native rank table differs')
 legal=img[0xC0742250-B:0xC0742298-B]
 if tuple(struct.unpack_from('<II',legal,i*8) for i in range(9)) != tuple(t[:2] for t in expected[1:]):
  raise ValueError('native legal/export table differs')
 pairs=img[0xC2E40224-B:0xC2E40274-B]
 if tuple(struct.unpack_from('<II',pairs,i*8) for i in range(10)) != tuple((v,i) for i,v in enumerate(STOCK_ORDER)) + ((0,9),):
  raise ValueError('native input pair table differs')
 for a in (0xC0CDACD8,0xC0D026F4):
  if struct.unpack_from('<9I',img,a-B) != STOCK_ORDER: raise ValueError('native rate list differs')
 # Row 9 (239.76) hands stock 119.88 (ROW240_VALUE); hidden internal 0 (15 fps) stays at row 10.
 pairs=pairs[:72]+struct.pack('<4I',ROW240_VALUE,9,0,10)
 return [('native_rank',RANK_TABLE,rank+struct.pack('<III',INTERNAL,EXPORT,RANK)),
         ('native_legal',LEGAL_TABLE,legal+struct.pack('<II',INTERNAL,EXPORT)),
         ('native_legal_descriptor',LEGAL_DESC,struct.pack('<II',LEGAL_TABLE,10)),
         ('native_input_pair',INPUT_PAIR,pairs),
         ('native_rate_list',RATE_LIST,struct.pack('<10I',*STOCK_ORDER,INTERNAL))]


def payloads():
 # Roles keep their HOOKS position; payloads of hooks that are not armed are not placed.
 return [(f'native_rate_{role}',str(Path(__file__).with_suffix('.S')),target)
         for role,(site,target,_,_,_) in enumerate(HOOKS,1) if site not in NOT_ARMED]


def defines():
 return {f'native_rate_{role}':[f'ROLE={role}',f'FLAG={FLAG:#x}',
         f'FMTLATCH={FMTLATCH:#x}',f'LIST={RATE_LIST:#x}',
         f'LEGAL_DESC={LEGAL_DESC:#x}',f'INPUT_PAIR={INPUT_PAIR:#x}',f'RATE240={RATE240:#x}',
         f'SUMMARY_STATE={SUMMARY_STATE_10:#x}'] for role in range(1,len(HOOKS)+1)}


def blobs():
 d=defines()
 out={name:assemble(src,defines=d[name]) for name,src,_ in payloads()}
 if any(len(blob)>0x80 for blob in out.values()): raise ValueError('native rate slot overflow')
 return out


def patches(img):
 for a,stock,note in MAPPING_SITES:
  if _word(img,a)!=stock: raise ValueError(f'{note}: stock word differs at {a:#x}')
 for a,_,stock,_,note in HOOKS:
  if _word(img,a)!=stock: raise ValueError(f'{note}: stock word differs at {a:#x}')
 values=(_mov(1,RANK_TABLE&0xffff),_mov(1,RANK_TABLE>>16,True),0xE3A0300B,
         _mov(2,INPUT_PAIR&0xffff),_mov(2,INPUT_PAIR>>16,True),0xE3A0200B)
 return [(a,v,note) for (a,_,note),v in zip(MAPPING_SITES,values)] + switch_patches(img) + [
         (a,_b(a,target),note) for a,target,_,_,note in HOOKS]


def installed_words(img):
 """Test-only convenience; exact-card verification should pass decoded card words."""
 out={a:w for a,w,_ in patches(img) if a not in NOT_ARMED}
 compiled=blobs()
 chunks=tables(img)+[(name,a,compiled[name]) for name,_,a in payloads()]
 for _,addr,blob in chunks:
  out.update((addr+i,struct.unpack_from('<I',blob,i)[0]) for i in range(0,len(blob),4))
 return out

FRCLASS_HOOK, FRCLASS_STOCK = HOOKS[0][0], HOOKS[0][2]
FRMAX_HOOK, FRMAX_STOCK = HOOKS[1][0], HOOKS[1][2]

LEGAL_HOOK, LEGAL_STOCK = HOOKS[4][0], HOOKS[4][2]
