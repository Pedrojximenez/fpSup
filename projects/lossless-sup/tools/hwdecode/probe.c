/* One hardware lossless-JPEG decode, run once from the USB shell (callfn).
 *
 * The firmware's own decode path, as XC_PlayFuncSeqDngDeveloping (C03C8350)
 * drives it for a Compression=7 still DNG: init C05A6890 with the decode flag
 * (word 8 = 1; the raw buffer in word 5, the compressed stream in word 6),
 * then C05A69E0 {width, height, format, tile w, tile h}, which blocks until the
 * engine is done and returns 1 on success.
 *
 * Here the stream comes straight from a recorded fpLossless frame: the file is
 * read whole into a 1 KiB aligned buffer, and its tiles are one contiguous
 * stream from the first tile offset (0x13400, 1 KiB aligned). Task context
 * only (file I/O, blocking wait). mode 0: allocate, read, decode, keep the
 * buffer for the host to save; mode 1: free it; mode 2: as 0, but the decode
 * is C062FAD0's own steps for ONE band with the height as given. C062FAD0
 * itself takes the last band's height as height % (tile h * rows), which is
 * 0 -- refused -- for a tile-padded height, and short of the last tile row
 * (which then loses its place in the stream) for the real one. */
#include <stdint.h>

struct hwd {
    uint32_t mode;
    uint32_t path[16];                  /* NUL-terminated, e.g. \CINEMA\... */
    uint32_t file_bytes, stream_off, out_bytes;
    uint32_t w, h, fmt, tw, th;
    /* results */
    uint32_t stage, obj[4], base, file, out, actual, open_ok, read_ok;
    uint32_t init_ret, dec_ret, t_read0, t_dec0, t_dec1;
    /* mode 2: C062FAD0's steps, one band, the height as given */
    uint32_t engine[4], flag, open_r, submit_r, start_r, pattern, close_r;
    uint32_t tiles;                     /* host-computed: no division here */
    /* before decoding: big-endian 16-bit `patch_val` at these file offsets
     * (the SOF3 line count of the last tile row), in memory only */
    uint32_t patch_n, patch_val, patch_at[16];
    /* mode 3: decode file[sub_off, +sub_len) copied to a 1 KiB aligned spot */
    uint32_t sub_off, sub_len, sub;
};

typedef uint32_t (*fn0)(void);
#define TIMER() ((fn0)0xc002b6e0u)()                      /* 1 MHz, ARM */

__attribute__((used))
uint32_t hwd_entry(struct hwd *p) {
    typedef uint32_t (*alloc_fn)(uint32_t *, uint32_t, uint32_t, uint32_t, uint32_t);
    typedef uint32_t (*addr_fn)(uint32_t *);
    typedef void (*free_fn)(uint32_t *, uint32_t);
    typedef void (*ctor_fn)(uint32_t, uint32_t);
    typedef uint32_t (*open_fn)(uint32_t, const char *, uint32_t);
    typedef uint32_t (*read_fn)(uint32_t, uint32_t, uint32_t, uint32_t *);
    typedef void (*close_fn)(uint32_t);
    typedef uint32_t (*init_fn)(volatile uint32_t *);
    volatile uint32_t init[9], dec[5];
    uint32_t file_room, fobj;

    if (p->mode == 1) {                                  /* give it back */
        if (p->base) ((free_fn)0xc001d7a0u)(p->obj, 2);
        p->base = 0;
        p->stage = 100;
        return 0;
    }
    p->stage = 1;
    file_room = (p->file_bytes + 0x3ffu) & ~0x3ffu;
    ((alloc_fn)0xc001d740u)(p->obj, 10, 0x1000u + file_room + ((p->out_bytes + 0x3ffu) & ~0x3ffu) +
                            ((p->sub_len + 0x3ffu) & ~0x3ffu), 0x400u, 0);
    p->base = ((addr_fn)0xc001d7f0u)(p->obj);
    if (!p->base || (p->base & 0x3ffu)) return p->stage = 2;
    fobj = p->base;
    p->file = p->base + 0x1000u;
    p->out = p->file + file_room;
    p->sub = p->out + ((p->out_bytes + 0x3ffu) & ~0x3ffu);

    p->stage = 3;
    ((ctor_fn)0xc0365e90u)(fobj, 1);
    p->open_ok = ((open_fn)0xc0365fb0u)(fobj, (const char *)p->path, 1);
    p->t_read0 = TIMER();
    if (p->open_ok) {
        p->read_ok = ((read_fn)0xc0366060u)(fobj, p->file, p->file_bytes, &p->actual);
        ((close_fn)0xc0366020u)(fobj);
    }
    ((ctor_fn)0xc0365ed0u)(fobj, 2);                     /* the destructor, (o, 2) */
    if (!p->open_ok || !p->read_ok || p->actual != p->file_bytes) return p->stage = 4;

    for (uint32_t n = 0; n < p->patch_n && n < 16; ++n) {
        volatile uint8_t *b = (volatile uint8_t *)(p->file + p->patch_at[n]);
        b[0] = (uint8_t)(p->patch_val >> 8);
        b[1] = (uint8_t)p->patch_val;
    }
    p->stage = 5;
    init[0] = p->w; init[1] = p->h; init[2] = p->fmt; init[3] = p->tw; init[4] = p->th;
    init[5] = p->out;                                    /* raw, written */
    init[6] = p->file + p->stream_off;                   /* compressed, read */
    if (p->mode == 3) {
        volatile uint8_t *d = (volatile uint8_t *)p->sub;
        const volatile uint8_t *s = (const volatile uint8_t *)(p->file + p->sub_off);
        for (uint32_t n = 0; n < p->sub_len; ++n) d[n] = s[n];
        init[6] = p->sub;
    }
    init[7] = 0;
    init[8] = 1;                                         /* decode */
    p->init_ret = ((init_fn)0xc05a6890u)(init);
    if (p->init_ret != 1) return p->stage = 6;

    if (p->mode == 2 || p->mode == 3) {
        typedef uint32_t (*clr_fn)(uint32_t, uint32_t);
        typedef uint32_t (*wai_fn)(uint32_t, uint32_t, uint32_t, uint32_t *, uint32_t);
        volatile uint32_t req[12];
        p->stage = 10;
        for (uint32_t n = 0; n < 4; ++n)
            p->engine[n] = *(volatile uint32_t *)(0xc302cdd4u + 4u * n);
        p->flag = ((fn0)0xc062f441u)();
        *(volatile uint32_t *)0xc302cdecu = p->tiles;
        for (uint32_t n = 0; n < 12; ++n) req[n] = 0;
        req[0] = p->w; req[1] = p->h; req[2] = p->fmt; req[3] = p->tw; req[4] = p->th;
        for (uint32_t n = 0; n < 4; ++n) req[5 + n] = p->engine[n];
        req[11] = 0xc062fce1u;                           /* the decoder's callback */
        ((clr_fn)0xc00169c8u)(p->flag, 0);
        p->open_r = ((fn0)0xc062fe71u)();
        if (p->open_r) return p->stage = 11;
        p->t_dec0 = TIMER();
        p->submit_r = ((init_fn)0xc062fec1u)(req);
        if (!p->submit_r) p->start_r = ((fn0)0xc062fed9u)();
        if (!p->submit_r && !p->start_r)
            p->dec_ret = ((wai_fn)0xc0016c08u)(p->flag, 2, 1, &p->pattern, 1000);
        p->t_dec1 = TIMER();
        ((clr_fn)0xc00169c8u)(p->flag, 0);
        p->close_r = ((fn0)0xc062fe81u)();
        return p->stage = (!p->submit_r && !p->start_r && !p->dec_ret) ? 8 : 12;
    }
    p->stage = 7;
    dec[0] = p->w; dec[1] = p->h; dec[2] = p->fmt; dec[3] = p->tw; dec[4] = p->th;
    p->t_dec0 = TIMER();
    p->dec_ret = ((init_fn)0xc05a69e0u)(dec);
    p->t_dec1 = TIMER();
    p->stage = p->dec_ret == 1 ? 8 : 9;
    return p->stage;
}
