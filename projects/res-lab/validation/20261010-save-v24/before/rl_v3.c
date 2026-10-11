/* Calculation-only res-lab. UI navigation and owned state; no recording core.
 * RCD1 version 3, consumed by res-custom/ogc.c. Neither the calculator nor the
 * exporter modifies sensor tables, settings, profiles or receiver registers. */
#include <stdint.h>
#define SL_SVC_BUTTON 1
#include "sloader.h"
#include "rl_rcd.h"
#include "virtual_rcd.h"

struct rl_asset { uint32_t name, pixels, w, h; };
struct rl_tab {
    uint32_t magic, version, calc_off, state_off, area_off, area_bytes;
    uint32_t pack_off, pack_len, atlas_off, export_off, fobj_off, back_off, cap;
    uint32_t stock_gui, stock_page, block, init, saves, failures, last_size;
    struct rl_asset assets[5];
    uint32_t reserved[8];
};

/* Words in the product's USER block, PC-relative even after relocation. */
__asm__(
    ".text\n.balign 4\n.arm\n"
    "rl_gui_layer:\n"
    "cmp r1, #0\nbeq 1f\n"
    "ldrb ip, [r1]\ncmp ip, #0x53\nldrbeq ip, [r1, #1]\ncmpeq ip, #0x4c\n"
    "ldrbeq ip, [r1, #2]\ncmpeq ip, #0x5f\nmoveq r0, #36\nbxeq lr\n"
    "1: ldr ip, rl_gui_next\nbx ip\n"
    "rl_gui_next: .word 0\n"
    ".thumb\n.thumb_func\nrl_page_layer:\n"
    "push {r0-r4, lr}\nmov r4, sp\nbic r12, r4, #7\nmov sp, r12\n"
    "ldr r0, rl_calc_menu\nbl rl_prepare\nmov sp, r4\npop {r0-r4, lr}\n"
    "ldr r12, rl_page_next\ncmp r12, #0\nbne 2f\n"
    "push.w {r4-r7, r11, lr}\nldr r12, rl_page_back\n"
    "2: bx r12\n.size rl_page_layer, .-rl_page_layer\n.balign 4\n"
    "rl_page_next: .word 0\nrl_page_back: .word 0xc05e82f5\n"
    "rl_calc_menu: .word 0\n");
extern const uint8_t rl_gui_layer[], rl_page_layer[];
extern const uintptr_t rl_gui_next, rl_page_next, rl_calc_menu;

static inline void rl_wr(uintptr_t a, uint32_t v) { *(volatile uint32_t *)a = v; }
static inline uint32_t rl_rd(uintptr_t a) { return *(volatile const uint32_t *)a; }
static void rl_zero(uint8_t *p, uint32_t n) { for (uint32_t i = 0; i < n; i++) p[i] = 0; }
static void rl_copy(uint8_t *d, const uint8_t *s, uint32_t n) { for (uint32_t i = 0; i < n; i++) d[i] = s[i]; }
static uint32_t rl_hash(const uint8_t *p, uint32_t n) {
    uint32_t h = 2166136261u;
    for (uint32_t i = 0; i < n; i++) h = (h ^ p[i]) * 16777619u;
    return h;
}
static uint32_t rl_div(uint32_t n, uint32_t d) {
    uint32_t q=0,bit=1;
    if (!d) return 0;
    while (!(d & 0x80000000u) && d<n) { d<<=1; bit<<=1; }
    while (bit) { if (n>=d) { n-=d; q|=bit; } d>>=1; bit>>=1; }
    return q;
}
static uint32_t rl_num(char *p, uint32_t v) {
    uint32_t n = 0, d = 1000u, begun = 0;
    for (; d; d /= 10u) {
        uint32_t q = rl_div(v,d);
        if (q || begun || d == 1) { p[n++] = '0' + q; begun = 1; }
        v -= q * d;
    }
    p[n] = 0; return n;
}
static uint32_t rl_status(struct sl_menu *m, uint32_t code) {
    char *p = m->export_text;
    rl_zero((uint8_t *)p, 32);
    /* Persistent text, since the GUI queue borrows it. */
    volatile uint32_t *words = (volatile uint32_t *)p;
    if (code == 0) { words[0] = 0x64616552u; words[1] = 0x00000079u; }
    else if (code == 1) { words[0] = 0x65766153u; words[1] = 0x00002064u; }
    else if (code == 2) { words[0] = 0x7373694du; words[1] = 0x20676e69u; words[2] = 0x43534552u; words[3] = 0x66205355u; words[4] = 0x65646c6fu; words[5] = 0x00000072u; }
    else if (code == 3) { words[0] = 0x20444352u; words[1] = 0x656d616eu; words[2] = 0x75662073u; words[3] = 0x00006c6cu; }
    else if (code == 4) { words[0] = 0x75736e55u; words[1] = 0x726f7070u; words[2] = 0x20646574u; words[3] = 0x7074756fu; words[4] = 0x00007475u; }
    else if (code == 5) { words[0] = 0x74697257u; words[1] = 0x65762065u; words[2] = 0x79666972u; words[3] = 0x69616620u; words[4] = 0x0064656cu; }
    else if (code == 6) { words[0] = 0x622d3431u; words[1] = 0x75207469u; words[2] = 0x7075736eu; words[3] = 0x74726f70u; words[4] = 0x00006465u; }
    /* Save completes this prefix with the filename before publishing. The
     * native publisher snapshots the string at this call, not on next draw. */
    if (code != 1u)
        ((uint32_t (*)(uint32_t, uintptr_t, uintptr_t))0xC0593FE0u)(0, (uintptr_t)m->names[49], (uintptr_t)p);
    return code;
}

/* Render white/alpha glyphs into the literal-only XCI payload. Each format has
 * its own LABnnn tiles and numeric resources; arbitrary edited dimensions do
 * not fall back to a missing stock imageSize resource. */
static void rl_draw(uint8_t *pack, const struct rl_tab *t, uint32_t k, const char *text) {
    const struct rl_asset *a = t->assets + k;
    uint32_t small = k < 2, cw = small ? 10u : 18u, ch = small ? 18u : 28u, n = 0;
    while (text[n]) n++;
    uint32_t x0 = (a->w - n * cw) / 2u, y0 = (a->h - ch) / 2u;
    const uint8_t *atlas = (const uint8_t *)(uintptr_t)(t->block + t->atlas_off + (small ? 0u : 21u * 10u * 18u));
    for (uint32_t i = 0; i < n; i++) {
        uint32_t c = text[i], g = c == 'L' ? 10u : c == 'A' ? 11u : c == 'B' ? 12u :
                                  c == 'V' ? 13u : c == 'R' ? 14u : c == 'C' ? 15u :
                                  c == 'U' ? 16u : c == 'S' ? 17u : c == 'T' ? 18u :
                                  c == 'O' ? 19u : c == 'M' ? 20u : c - '0';
        if (g > 20u) continue;
        for (uint32_t y = 0; y < ch; y++) for (uint32_t x = 0; x < cw; x++) {
            uint8_t v = atlas[g*cw*ch + y*cw + x];
            uint32_t at = a->pixels + 2u * ((y0+y)*a->w + x0 + i*cw + x);
            pack[at] = pack[at+1] = v;
        }
    }
}

/* Validate physical geometry before publishing a calculator-generated RCD.
 * The common consumer validates its wire format, not a producer's formula. */
static uint32_t rl_canvas_safe(const struct sl_menu *m) {
    const uint32_t *c = m->canvas;
    uint32_t w=m->ro_w, h=m->ro_h, zh=c[13], zv=c[20], ph, pv, sw, sh;
    if (!w || w>6064u || !h || h>4096u || m->crop_w>=w || m->crop_h>=h) return 0;
    if ((m->bin_h!=1u && m->bin_h!=3u) || (m->bin_v!=1u && m->bin_v!=3u)) return 0;
    if (m->bin_kh>=6u || m->bin_kv>=6u || m->bin_mode>1u) return 0;
    if (m->out_w+16u > (rl_div(w-m->crop_w,m->bin_h)&~15u) ||
        m->out_h+10u > (rl_div(h-m->crop_h,m->bin_v)&~1u)) return 0;
    if (zh<1023u || zh>16384u || zv<1023u || zv>16384u ||
        c[12]<1023u || c[12]>16384u || c[19]<1023u || c[19]>16384u) return 0;
    if (c[10]>1u || c[17]>1u || c[11]!=(m->bin_h==3u) || c[18]!=(m->bin_v==3u)) return 0;
    if (zh<1024u) zh=1024u;
    if (zv<1024u) zv=1024u;
    if (c[0]!=(rl_div(rl_div(w,m->bin_h)*1024u,zh)&~15u) ||
        c[1]!=(rl_div(rl_div(h,m->bin_v)*1024u,zv)&~1u)) return 0;
    if (c[0]<m->out_w+16u || c[1]<m->out_h+10u || c[6]!=m->out_w || c[8]!=m->out_h) return 0;
    ph=(c[10]?3u:1u)*(c[12]<1024u?1024u:c[12]);
    pv=(c[17]?3u:1u)*(c[19]<1024u?1024u:c[19]);
    /* Without binning, unequal preview scales reintroduce r77/v11's brief
     * record-start seam. Binned output still requires the exact record tap. */
    if (m->bin_h==1u && m->bin_v==1u && ph!=pv) return 0;
    if ((m->bin_h>1u || m->bin_v>1u) && rl_div(w*1024u,m->bin_h*zh)<=2100u &&
        (c[10]!=c[11] || c[17]!=c[18] || (c[12]<1024u?1024u:c[12])!=zh ||
         (c[19]<1024u?1024u:c[19])!=zv)) return 0;
    sw=rl_div(w*1024u,ph); sh=rl_div(h*1024u,pv);
    if (sw>2100u || !c[5] || c[5]>2000u || (c[5]&15u) || !c[7] ||
        c[2]!=c[5]+16u || c[3]!=c[7]+10u || c[2]>sw || c[3]>sh) return 0;
    if (c[21]!=c[2] || c[22]!=c[0] || c[23]!=c[3] || c[24]!=c[1] || c[25]!=w || c[26]!=h) return 0;
    if (!m->sb_vis_w || m->sb_vis_w>2000u || !m->sb_vis_h || m->sb_vis_h>1334u) return 0;
    return c[4]==1u && c[9]==(c[10]?16u:1u) && !c[14] && c[15]==1u && !c[16];
}

/* All offsets and strings here follow rcd.py's reference encoder. One selected
 * stock mode, ceiling = 72MHz / (hmax * (raster rows + blanking)). No per-rate
 * timing guesses: res-custom generates the supported rates itself. */
__attribute__((used)) static uint32_t rl_encode(struct sl_menu *m, const char *lab) {
    struct rl_tab *t = (struct rl_tab *)m->export_ctx;
    uint8_t *b = (uint8_t *)(uintptr_t)(t->block + t->export_off);
    uintptr_t desc = rl_rd(0xC343B588u), meta = desc ? rl_rd(desc+8) : 0, tm = desc ? rl_rd(desc) : 0;
    uint32_t cnt = desc ? rl_rd(desc+12) : 0, donor, hm = 0, mx = 0, x = 0;
    t->reserved[0] = 4;
    if (!m->canvas_valid || !m->out_w || !m->out_h || m->out_w > 6064u || m->out_h > 4040u ||
        (m->out_w & 15u) || (m->out_h & 1u) || !m->modes_rows || m->mode_sel >= m->modes_rows ||
        !meta || !tm || cnt > 256u) return 0;
    if (!rl_canvas_safe(m)) return 0;
    donor = m->mode_ids[m->mode_sel];
    for (uint32_t i = 0; i < cnt && i < 70u; i++) if (rl_rd(meta+100*i) == donor) {
        /* Current res-custom supports CinemaDNG 8/10/12, not native 14-bit. */
        if (rl_rd(meta+100*i+0x3c) == 1u) { t->reserved[0]=6; return 0; }
        if (rl_rd(meta+100*i+4)!=m->ro_w || rl_rd(meta+100*i+8)!=m->ro_h ||
            rl_rd(meta+100*i+0x4c)!=m->ro_sx || rl_rd(meta+100*i+0x50)!=m->ro_sy) return 0;
        hm = rl_rd(tm+32*i+4) & 0xffffu; x = rl_rd(tm+32*i+8) >> 16;
        uint32_t den = hm * (rl_rd(meta+100*i+8) + rl_rd(meta+100*i+0x5c));
        if (!den) return 0;
        uint32_t q = rl_div(72000000u,den);
        mx = q * 100u + rl_div((72000000u-q*den)*100u,den);
        break;
    }
    if (!hm || mx < 1798u || mx > 100000u || t->pack_len + 1024u > t->cap) return 0;
    rl_zero(b, t->cap);
    const uint32_t md = 224u, cv = 248u, ui = 640u, sb = 688u, rc = 744u, bf = 880u, pk = 960u;
    uint32_t len = (pk + t->pack_len + 3u) & ~3u;
    /* Seven required sections: binning is shared by disk and virtual RCDs. */
    volatile uint32_t types[7];
    types[0]=RLC_SEC_MODES; types[1]=RLC_SEC_CANVAS; types[2]=RLC_SEC_UI;
    types[3]=RLC_SEC_STANDBY; types[4]=RLC_SEC_RATECANVAS; types[5]=RLC_SEC_PACK;
    types[6]=RLC_SEC_BINFILT;
    volatile uint32_t offs[7];
    offs[0]=md; offs[1]=cv; offs[2]=ui; offs[3]=sb; offs[4]=rc; offs[5]=pk;;
    offs[6]=bf;
    volatile uint32_t lens[7];
    lens[0]=24; lens[1]=32+8*(29+13); lens[2]=48; lens[3]=52; lens[4]=124; lens[5]=t->pack_len;;
    lens[6]=20;
    for (uint32_t i = 0; i < 7; i++) {
        rl_wr((uintptr_t)b+64+16*i, types[i]); rl_wr((uintptr_t)b+68+16*i, offs[i]);
        rl_wr((uintptr_t)b+72+16*i, lens[i]); rl_wr((uintptr_t)b+76+16*i, 1);
    }
    rl_wr((uintptr_t)b+RLC_H_MAGIC, RLC_MAGIC); rl_wr((uintptr_t)b+RLC_H_VERSION, RLC_VERSION);
    rl_wr((uintptr_t)b+RLC_H_HLEN, RLC_HDR); rl_wr((uintptr_t)b+RLC_H_FLEN, len);
    rl_wr((uintptr_t)b+RLC_H_NSEC, 7); rl_wr((uintptr_t)b+RLC_H_SECOFF, RLC_HDR);
    rl_wr((uintptr_t)b+bf,m->bin_h);rl_wr((uintptr_t)b+bf+4,m->bin_v);
    rl_wr((uintptr_t)b+bf+8,m->bin_kh);rl_wr((uintptr_t)b+bf+12,m->bin_kv);rl_wr((uintptr_t)b+bf+16,m->bin_mode);
    rl_wr((uintptr_t)b+RLC_H_STOCK, 2); /* record under stock FHD; core uses virtual profiles */
    uint32_t aspect = rl_div(m->out_w * 1024u,m->out_h);
    rl_wr((uintptr_t)b+RLC_H_ASPECT, aspect > 1934u ? 9u : aspect > 1678u ? 3u : 2u);
    rl_wr((uintptr_t)b+RLC_H_FLAGS, 1); rl_wr((uintptr_t)b+RLC_H_PROFILE, 83);
    rl_wr((uintptr_t)b+RLC_H_MINCORE, RLC_CORE_VERSION);
    rl_copy(b+RLC_H_LABEL, (const uint8_t *)lab, 6);
    rl_wr((uintptr_t)b+RLC_H_ENUM, 0x524C0000u + (lab[3]-'0')*100u + (lab[4]-'0')*10u + lab[5]-'0');
    rl_wr((uintptr_t)b+RLC_H_MAXRATE, mx);
    rl_wr((uintptr_t)b+md, 1); rl_wr((uintptr_t)b+md+4, donor); rl_wr((uintptr_t)b+md+8, mx);
    rl_wr((uintptr_t)b+md+12, hm); rl_wr((uintptr_t)b+md+20, x);
    rl_wr((uintptr_t)b+cv, 0); rl_wr((uintptr_t)b+cv+4, m->out_w); rl_wr((uintptr_t)b+cv+8, m->out_h);
    rl_wr((uintptr_t)b+cv+12, 29); rl_wr((uintptr_t)b+cv+16, 13);
    volatile uint32_t fields[29];
    fields[0]=0; fields[1]=4; fields[2]=12; fields[3]=16; fields[4]=28; fields[5]=32; fields[6]=36; fields[7]=40; fields[8]=44; fields[9]=56; fields[10]=88; fields[11]=92; fields[12]=96; fields[13]=100; fields[14]=136; fields[15]=144; fields[16]=192; fields[17]=196; fields[18]=200; fields[19]=208; fields[20]=212; fields[21]=216; fields[22]=220; fields[23]=224; fields[24]=228; fields[25]=244; fields[26]=248; fields[27]=252; fields[28]=256;;
    for (uint32_t i = 0; i < 29; i++) {
        rl_wr((uintptr_t)b+cv+32+8*i, fields[i]); rl_wr((uintptr_t)b+cv+36+8*i, m->canvas[i]);
    }
    volatile uint32_t pbf[13];
    pbf[0]=28; pbf[1]=12; pbf[2]=16; pbf[3]=216; pbf[4]=224; pbf[5]=32; pbf[6]=40; pbf[7]=244; pbf[8]=248; pbf[9]=96; pbf[10]=208; pbf[11]=100; pbf[12]=212;;
    volatile uint32_t pbv[13];
    pbv[0]=2; pbv[1]=m->canvas[0]; pbv[2]=m->canvas[1]; pbv[3]=m->canvas[0]; pbv[4]=m->canvas[1]; pbv[5]=m->out_w; pbv[6]=m->out_h; pbv[7]=m->canvas[0]; pbv[8]=m->canvas[1]; pbv[9]=1024; pbv[10]=1024; pbv[11]=1024; pbv[12]=1024;;
    for (uint32_t i = 0; i < 13; i++) {
        rl_wr((uintptr_t)b+cv+32+8*(29+i), pbf[i]); rl_wr((uintptr_t)b+cv+36+8*(29+i), pbv[i]);
    }
    rl_copy(b+ui, (const uint8_t *)lab, 6); b[ui+6] = ' ';
    uint32_t n = 7 + rl_num((char *)b+ui+7, m->out_w); b[ui+n++] = 'x';
    rl_num((char *)b+ui+n, m->out_h); rl_copy(b+ui+32, (const uint8_t *)lab, 6);
    /* Explicit standby width and height, computed alongside preview geometry. */
    volatile uint32_t pids[6];
    pids[0]=5; pids[1]=210; pids[2]=227; pids[3]=257; pids[4]=258; pids[5]=259;;
    rl_wr((uintptr_t)b+sb, 1); rl_wr((uintptr_t)b+sb+4, 6); rl_wr((uintptr_t)b+sb+8, 2);
    for (uint32_t i = 0; i < 6; i++) rl_wr((uintptr_t)b+sb+12+4*i, pids[i]);
    rl_wr((uintptr_t)b+sb+36, 0x20); rl_wr((uintptr_t)b+sb+40, m->sb_vis_w);
    rl_wr((uintptr_t)b+sb+44, 0x28); rl_wr((uintptr_t)b+sb+48, m->sb_vis_h);
    /* The core uses the first matching selector. Exact high rates must
     * precede the rank-zero wildcard, which is the low-rate fallback. */
    volatile uint32_t ranks[5];
    ranks[0]=10000; ranks[1]=11988; ranks[2]=23976; ranks[3]=27972; ranks[4]=0;;
    rl_wr((uintptr_t)b+rc, 5);
    for (uint32_t i=0; i<5; i++) {
        uintptr_t r=(uintptr_t)b+rc+4+24*i;
        rl_wr(r,ranks[i]); rl_wr(r+12,1); rl_wr(r+16,0xB0); rl_wr(r+20,i < 4u ? 1u : 0u);
    }
    rl_copy(b+pk, (const uint8_t *)(uintptr_t)(t->block+t->pack_off), t->pack_len);
    uint8_t *pack = b+pk;
    const char *tile=lab;
#if defined(RL_VIRTUAL_RCD)
    volatile uint32_t display[2]; display[0]=0x54535543u; display[1]=0x00004d4fu; /* CUSTOM */
    if(lab[0]=='V')tile=(const char *)display;
#endif
    for (uint32_t k = 0; k < 3; k++) { rl_copy(pack+t->assets[k].name, (const uint8_t *)lab, 6); rl_draw(pack,t,k,tile); }
    char digits[5];
    for (uint32_t k = 3; k < 5; k++) {
        uint32_t val = k == 3 ? m->out_w : m->out_h;
        rl_num(digits,val);
        uint8_t *name = pack+t->assets[k].name;
        rl_zero(name+17, 4); /* prefix font_S_imageSize_ has 17 chars */
        uint32_t j = 0; while (digits[j]) { name[17+j]=digits[j]; j++; }
        if (k == 4 && m->out_w == m->out_h) { name[0]='L'; name[1]='A'; name[2]='B'; name[3]='_'; name[4]='H'; name[5]=0; }
        rl_draw(pack,t,k,digits);
    }
    rl_wr((uintptr_t)b+RLC_H_SUM, rl_hash(b+RLC_HDR,len-RLC_HDR));
    t->last_size = len;
    return len;
}

/* The first producer of the common service. Output is borrowed only for this
 * call; res-custom copies it into its own staging and immutable asset store. */
static uint32_t rl_virtual_build(uintptr_t context,const struct vrc_input *in,struct vrc_blob *out) {
    struct sl_menu *m=(struct sl_menu *)context;
    if (!in || in->abi!=VRC_ABI || in->bytes!=sizeof(*in)) return 4;
    char lab[8]; lab[0]='V';lab[1]='R';lab[2]='C';lab[3]='0';lab[4]='0';lab[5]='0';lab[6]=lab[7]=0;
    uint32_t len=rl_encode(m,lab);
    struct rl_tab *t=(struct rl_tab *)m->export_ctx;
    if (!len) return t->reserved[0] ? t->reserved[0] : 4;
    out->data=t->block+t->export_off; out->bytes=len;
    return 0;
}
static uint32_t rl_virtual_settings(uintptr_t context,uint32_t open) {
    struct sl_menu *m=(struct sl_menu *)context;
    if (m->result!=SL_MENU_INSTALLED || m->pages_state!=1u)
        return open ? VRC_NOT_READY : 0u;
    if (!open) return 36u;
    if (*(volatile uint8_t *)0xC347E08Fu) return VRC_BUSY;
    struct rl_tab *t=(struct rl_tab *)m->export_ctx;
    const char *name=(const char *)(t->reserved+4);
    /* The stock controlAppState action performs BOTH an application request
     * and a view-state event. gui send alone performs only the former.
     * SupManager invokes this callback on the UI thread. */
    uintptr_t gui=((uintptr_t (*)(void))0xC054DD38u)();
    if (!gui) return VRC_NOT_READY;
    uint32_t sent=((uint32_t (*)(uintptr_t,const char *))rl_rd(rl_rd(gui)+12u))(gui,name);
    if (!sent) return VRC_NOT_READY;
    uint32_t rc=((uint32_t (*)(uintptr_t,const char *,uint32_t,uint32_t))0xC05DCB41u)(m->app,name,0,0);
    return rc ? VRC_NOT_READY : VRC_OK;
}

static int rl_settings_button(void *ctx) {
    return (int)rl_virtual_settings((uintptr_t)ctx,1);
}

__attribute__((used)) static uint32_t sl_menu_apply(struct sl_menu *m) {
    struct rl_tab *t=(struct rl_tab *)m->export_ctx;
    const struct vrc_endpoint *e=(const struct vrc_endpoint *)(uintptr_t)t->reserved[1];
    uint32_t result=e ? e->dispatch(e->context,VRC_APPLY,0x42414c52u) : VRC_NOT_READY;
    t->reserved[3]=result;
    char *p=m->export_text;
    rl_zero((uint8_t *)p,32);
    /* No transient strings are handed to the GUI queue. */
    volatile uint32_t *w=(volatile uint32_t *)p;
    if (result==VRC_OK) { w[0]=0x6c707041u; w[1]=0x00646569u; }
    else if (result==VRC_BUSY || result==VRC_REENTER) { w[0]=0x6f636552u; w[1]=0x6e696472u; w[2]=0x202f2067u; w[3]=0x79737562u; w[4]=0x00000000u; }
    else if (result==VRC_RATE) { w[0]=0x20535046u; w[1]=0x75736e75u; w[2]=0x726f7070u; w[3]=0x00646574u; }
    else if (result==VRC_FORMAT) { w[0]=0x656c6553u; w[1]=0x43207463u; w[2]=0x6d656e69u; w[3]=0x474e4461u; w[4]=0x00000000u; }
    else if (result==VRC_FULL) { w[0]=0x6f6d654du; w[1]=0x66207972u; w[2]=0x006c6c75u; }
    else if (result==VRC_NOT_READY) { w[0]=0x76616e55u; w[1]=0x616c6961u; w[2]=0x00656c62u; }
    else { w[0]=0x69636552u; w[1]=0x72206570u; w[2]=0x63656a65u; w[3]=0x00646574u; }
    if (result==VRC_BUILD && t->reserved[0]==6u) { rl_status(m,6); return result; }
    ((uint32_t (*)(uint32_t,uintptr_t,uintptr_t))0xC0593FE0u)(0,(uintptr_t)m->names[49],(uintptr_t)p);
    return result;
}

/* Numeric edits update the diagram immediately; commit automatically when
 * their native editor finishes. Focus, tabs and filter-only changes never
 * restart a live view whose effective recipe has not changed. */
__attribute__((used,noinline)) static void sl_menu_auto(struct sl_menu *m) {
    if(!m->modes_rows || m->mode_sel>=m->modes_rows){rl_status(m,4);return;}
    uint32_t now[11]={m->mode_ids[m->mode_sel],m->out_w,m->out_h,m->crop_w,m->crop_h,m->bin_h,m->bin_v,m->canvas_valid,m->bin_kh,m->bin_kv,m->bin_mode};
    uint32_t same=m->applied_valid;
    for(uint32_t i=0;i<11u;i++)if(now[i]!=m->applied_geometry[i])same=0;
    if(same)return;
    if(m->editing || m->crop_editing) {
        volatile uint32_t *p=(volatile uint32_t *)m->export_text;
        rl_zero((uint8_t *)p,32);p[0]=0x74696445u;p[1]=0x20676e69u;p[2]=0x002e2e2eu; /* Editing ... */
        ((uint32_t (*)(uint32_t,uintptr_t,uintptr_t))0xC0593FE0u)(0,(uintptr_t)m->names[49],(uintptr_t)p);
        return;
    }
    if(sl_menu_apply(m)==VRC_OK){
        for(uint32_t i=0;i<11u;i++)m->applied_geometry[i]=now[i];
        m->applied_valid=1u;
    }
}

/* A fresh filename, exact-length readback; success never means only a prefix
 * matched. Native open/write/close errors leave a visible failure status. */
__attribute__((used)) static uint32_t sl_menu_export(struct sl_menu *m) {
    struct rl_tab *t = (struct rl_tab *)m->export_ctx;
    uintptr_t fo = t->block+t->fobj_off, dh = fo+0x400, ent = fo+0x420;
    uint8_t used[125]; rl_zero(used,125);
    volatile uint32_t root[5];
    root[0]=0x5370665cu; root[1]=0x525c7075u; root[2]=0x55435345u; root[3]=0x53u; root[4]=0u;; /* \fpSup\RESCUS */
    ((uint32_t (*)(uintptr_t,uint32_t))0xC0366918u)(dh,1);
    if (!((uint32_t (*)(uintptr_t,uintptr_t))0xC0366990u)(dh,(uintptr_t)root)) {
        ((uint32_t (*)(uintptr_t,uint32_t))0xC0366940u)(dh,2); t->failures++; return rl_status(m,2);
    }
    while (((uint32_t (*)(uintptr_t,uintptr_t))0xC03669F8u)(dh,ent)) {
        const uint16_t *p = (const uint16_t *)ent;
        if ((p[0]|32)=='l' && (p[1]|32)=='a' && (p[2]|32)=='b' && p[3]>='0' && p[3]<='9' &&
            p[4]>='0' && p[4]<='9' && p[5]>='0' && p[5]<='9' && p[6]=='.' &&
            (p[7]|32)=='r' && (p[8]|32)=='c' && (p[9]|32)=='d' && !p[10]) {
            uint32_t k = (p[3]-'0')*100+(p[4]-'0')*10+p[5]-'0'; used[k/8] |= 1u<<(k%8);
        }
    }
    ((uint32_t (*)(uintptr_t,uint32_t))0xC0366940u)(dh,2);
    uint32_t id; for (id=1; id<=999u && (used[id/8] & (1u<<(id%8))); id++) {}
    if (id>999u) { t->failures++; return rl_status(m,3); }
    char lab[8]; rl_zero((uint8_t *)lab,8);
    lab[0]='L'; lab[1]='A'; lab[2]='B'; lab[3]='0'+id/100; lab[4]='0'+id/10%10; lab[5]='0'+id%10;
    uint32_t len = rl_encode(m,lab);
    if (!len) { t->failures++; return rl_status(m,t->reserved[0] ? t->reserved[0] : 4u); }
    char path[32]; rl_zero((uint8_t *)path,32); rl_copy((uint8_t *)path,(const uint8_t *)root,13);
    path[13]='\\'; rl_copy((uint8_t *)path+14,(const uint8_t *)lab,6);
    path[20]='.'; path[21]='R'; path[22]='C'; path[23]='D';
    ((uint32_t (*)(uintptr_t,uint32_t))0xC0365E90u)(fo,1);
    uint32_t ok=0;
    if (((uint32_t (*)(uintptr_t,uintptr_t,uint32_t))0xC0365FB0u)(fo,(uintptr_t)path,7)) {
        ok = ((uint32_t (*)(uintptr_t,uintptr_t,uint32_t))0xC03660E8u)(fo,t->block+t->export_off,len) != 0;
        ((uint32_t (*)(uintptr_t))0xC0366020u)(fo);
    }
    ((uint32_t (*)(uintptr_t,uint32_t))0xC0365ED0u)(fo,2);
    uint32_t actual=0;
    ((uint32_t (*)(uintptr_t,uint32_t))0xC0365E90u)(fo,1);
    if (ok && ((uint32_t (*)(uintptr_t,uintptr_t,uint32_t))0xC0365FB0u)(fo,(uintptr_t)path,1)) {
        ((uint32_t (*)(uintptr_t,uintptr_t,uint32_t,uintptr_t))0xC0366060u)(fo,t->block+t->back_off,len+1,(uintptr_t)&actual);
        ((uint32_t (*)(uintptr_t))0xC0366020u)(fo);
        ok = actual == len;
        const uint8_t *a=(const uint8_t *)(uintptr_t)(t->block+t->export_off), *b=(const uint8_t *)(uintptr_t)(t->block+t->back_off);
        for (uint32_t i=0; ok && i<len; i++) if (a[i]!=b[i]) ok=0;
    } else ok=0;
    ((uint32_t (*)(uintptr_t,uint32_t))0xC0365ED0u)(fo,2);
    if (!ok) { t->failures++; return rl_status(m,5); }
    t->saves++; rl_status(m,1);
    rl_copy((uint8_t *)m->export_text+6,(const uint8_t *)lab,6);
    m->export_text[12]='.'; m->export_text[13]='R'; m->export_text[14]='C'; m->export_text[15]='D';
    ((uint32_t (*)(uint32_t, uintptr_t, uintptr_t))0xC0593FE0u)(0, (uintptr_t)m->names[49], (uintptr_t)m->export_text);
    return 1;
}

/* Real UI thread. Re-entrant page registration must not enter this twice. */
__attribute__((used)) static void rl_prepare(struct sl_menu *m) {
    if (!m || m->result != SL_MENU_INSTALLED) return;
    struct rl_tab *t=(struct rl_tab *)m->export_ctx;
    if (t->init) return;
    t->init=1;
    uintptr_t reader=0;
    uint32_t rc=((uint32_t (*)(uintptr_t,uintptr_t,uint32_t,uintptr_t))0xC05E84D9u)(m->app,m->nbr,m->nbr_len,(uintptr_t)&reader);
    if (rc) { t->init=3;
#if !defined(RL_VIRTUAL_RCD)
        rl_wr(m->entry+8,0x19c130u);
#endif
        return;
    }
    sl_menu_ui(m,0);
    t->init=m->pages_state == 1u ? 2u : 3u;
#if !defined(RL_VIRTUAL_RCD)
    if (t->init==3) rl_wr(m->entry+8,0x19c130u);
#endif
    if (t->init==2) { m->axis_armed=1; sl_menu_panel(m); rl_status(m,0); }
}

static uint32_t rl_bw(uint32_t site,uint32_t to) {
    uint32_t d=to-site-4,s=(d>>24)&1,i1=(d>>23)&1,i2=(d>>22)&1;
    return 0xF000u|s<<10|((d>>12)&0x3ff)| (0x9000u|((~(i1^s))&1)<<13|((~(i2^s))&1)<<11|((d>>1)&0x7ff))<<16;
}

int rl_v3_entry(uint8_t *block, const struct sl_svc *svc, const char *path) {
    (void)path;
    struct rl_tab *t=(struct rl_tab *)(block+RL_TAB_OFF);
    if (t->magic!=0x32434c52u || t->version!=2 || svc->version<3) return SL_RELEASE;
    if (svc->claim(svc,0xC056461Cu,4,&t->stock_gui,SL_CHAIN)!=SL_OK ||
        svc->claim(svc,0xC05E82F0u,4,&t->stock_page,SL_CHAIN)!=SL_OK) return SL_RELEASE;
    uint32_t gv=svc->cave_alloc(svc,8),pv=svc->cave_alloc(svc,8);
    if (!gv || !pv) return SL_RELEASE;
    t->block=(uintptr_t)block;
    struct sl_menu *m=(struct sl_menu *)(block+t->state_off);
    m->core_base=(uintptr_t)block+t->calc_off;
    m->export_ctx=(uintptr_t)t;
    t->reserved[4]=0x4C5F4C53u; t->reserved[5]=0x00004241u; /* SL_LAB */
#if defined(RL_VIRTUAL_RCD)
    if (svc->holder(svc,VRC_PICKER,0)) {
        const struct vrc_endpoint *e=vrc_find(RLC_CAVE_FIRST,RLC_CAVE_END);
        if (e) {
            struct vrc_provider p={sizeof(p),VRC_ABI,0x42414c52u,0,(uintptr_t)m,&rl_virtual_build,&rl_virtual_settings,0};
            t->reserved[2]=e->dispatch(e->context,VRC_REGISTER,(uintptr_t)&p);
            if (t->reserved[2]==VRC_OK) t->reserved[1]=(uintptr_t)e;
        }
    }
#endif
    if (sl_menu_install(m,(uintptr_t)block+t->area_off,t->area_bytes)!=SL_MENU_INSTALLED) return SL_KEEP;
    rl_wr((uintptr_t)&rl_calc_menu,(uintptr_t)m);
    rl_wr((uintptr_t)&rl_gui_next,svc->chain_next(svc,0xC056461Cu,0));
    rl_wr((uintptr_t)&rl_page_next,svc->chain_next(svc,0xC05E82F0u,1));
    rl_wr(gv,0xE51FF004u); rl_wr(gv+4,(uintptr_t)rl_gui_layer);
    rl_wr(pv,0xF000F8DFu); rl_wr(pv+4,(uintptr_t)rl_page_layer|1u);
    svc->publish(svc);
    rl_wr(0xC056461Cu,0xEB000000u|((gv-0xC0564624u)>>2 & 0xffffffu));
    rl_wr(0xC05E82F0u,rl_bw(0xC05E82F0u,pv));
    svc->publish(svc);
#if !defined(RL_VIRTUAL_RCD)
    rl_wr(m->entry+8,(uintptr_t)m->page-0xC18C0460u);
#endif
    svc->publish(svc);
#if defined(RL_VIRTUAL_RCD)
    if (svc->version>=4 && svc->button)
        svc->button(svc,rl_settings_button,m,(const char *)(t->reserved+4));
#endif
    return SL_KEEP;
}
