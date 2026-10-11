"""RES-CUSTOM's file list, using SupManager's native five-row page."""
import struct, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/'fpSup/uishare/tab'),str(HERE.parent)]
import ft6_page as F, manage_page as M, sl_pages as SL

VISIBLE, TABS = 5, 4                 # consumer catalogue holds at most 16 files
PARTS = ('N','G','V','R','E','Visible','Lock','Selected','More','Default','Choice','VersionX')
# This private descriptor order is also declared by ogc_files.c. Types are the
# native application's integer (0) and string (2), not Python object types.
VARIABLES = [('RC_Key',0),('RC_Focus',0),('RC_File',2),('RC_On',2),
             ('RC_Count',2),('RC_Status',2),('RC_Restart',2)]
VARIABLES += [(f'RC_{part}{k}',2 if i<5 else 0)
              for k in range(1,VISIBLE+1) for i,part in enumerate(PARTS)]
VARIABLES += [(f'RC_Tab{part}{k}',0)
              for part in ('Visible','Active','X','Width') for k in range(1,TABS+1)]
VARIABLES += [('RC_Title',2)]


def build():
    img,pool=F.stock_pool()
    # Build from the same donors, colours, numbered tabs, popup and typography
    # as SupManager. Restore the shared module option after this private build.
    old=M.PAGE_TABS
    header=M.manager_header
    def counted_header(pg,title_text='SupManager'):
        header(pg,title_text)
        title,field=next((r,o) for r,o,t in pg.refs if t==title_text)
        pg.refs=[(r,o,t) for r,o,t in pg.refs if r is not title or o!=field]
        F.put(title,field,0);title[field+4]=0
        owner=F.u32(title,20)
        pg.bind(pg.seq,owner,'RC_Title',F.u32(title,24),'text')
        pg.added.append(pg.seq[F.by_object(pg.seq)[owner][-1]])
    try:
        M.PAGE_TABS=TABS
        M.manager_header=counted_header
        page,refs=M.build_manage(img,pool)
    finally:
        M.PAGE_TABS=old
        M.manager_header=header
    page=bytearray(page)
    rename={'FT_Key':'RC_Key','FT_Focus':'RC_Focus','FT_OK':'RC_Status',
            'FT_Version':'RC_Count','FT_RightFooter':'RC_Restart',
            'SupManager':'RES-CUSTOM'}
    rename.update({f'FT_{part}{k}':f'RC_{part}{k}' for k in range(1,VISIBLE+1) for part in PARTS})
    rename.update({f'FT_Tab{part}{k}':f'RC_Tab{part}{k}'
                   for part in ('Visible','Active','X','Width') for k in range(1,TABS+1)})
    refs=[(off,rename.get(name,name)) for off,name in refs]
    for off,name in refs:
        F.put(page,off,pool.intern(name)[0])
    pack=SL.build_pack([('RC_FILES',bytes(page),'FT_LIST')])
    rows={n:o for n,o,_ in SL.native_rows(pack)}
    refs=[(rows['RC_FILES']+off,name) for off,name in refs]
    strings=list(dict.fromkeys(name for _,name in refs))
    if len(strings)>128:raise ValueError('file-list private string budget')
    if any(len(name)>=16 for name,_ in VARIABLES):raise ValueError('file-list variable name budget')
    out=bytearray(40)
    def place(b):
        out.extend(bytes(-len(out)%4));at=len(out);out.extend(b);return at
    str_off=place(b''.join(name.encode()+b'\0' for name in strings))
    ref_off=place(b''.join(struct.pack('<2I',off,strings.index(name)) for off,name in refs))
    name_off=place(b''.join(struct.pack('<I',typ)+name.encode().ljust(16,b'\0') for name,typ in VARIABLES))
    pack_off=place(pack)
    out[:40]=struct.pack('<10I',0x32464352,len(strings),len(refs),str_off,ref_off,
                         name_off,pack_off,len(pack),len(VARIABLES),20)
    return bytes(out),dict(strings=strings,refs=len(refs),page_bytes=len(page),pack_bytes=len(pack),
                          focus=F.ROW_ITEM,visible=VISIBLE,tabs=TABS,variables=VARIABLES)
