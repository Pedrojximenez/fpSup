/* Host fixture for test_wr.py: wr against fake firmware.  Never built for the
 * camera.  32-bit "addresses" below 0x20000000 map onto host arrays. */
#include <stdint.h>
#include <stdlib.h>
#include "wr.h"

#define VOL_AT  0x10000000u
#define MISC_AT 0x00002000u
#define OBJ_AT  0x00004000u            /* mgr + frame nodes (test_wr.py) */
static uint32_t g_vol[0x5000 / 4];
static uint32_t g_misc[16];
static uint32_t g_obj[0x8000 / 4];
static uint32_t g_junk;

volatile uint32_t *wr_host_mem(uint32_t a) {
    if (a >= VOL_AT && a < VOL_AT + sizeof g_vol) return &g_vol[(a - VOL_AT) / 4];
    if (a >= MISC_AT && a < MISC_AT + sizeof g_misc) return &g_misc[(a - MISC_AT) / 4];
    if (a >= OBJ_AT && a < OBJ_AT + sizeof g_obj) return &g_obj[(a - OBJ_AT) / 4];
    g_junk = 0xDEAD0000u | (a & 0xFFFF);
    return &g_junk;
}
uint32_t fx_rd(uint32_t a) { return *wr_host_mem(a); }
void     fx_wr(uint32_t a, uint32_t v) { *wr_host_mem(a) = v; }

static uint32_t irq_off(void) { return 0x13; }
static void irq_restore(uint32_t s) { (void)s; }

typedef uint32_t (*acq_t)(void);
typedef int (*add_t)(uint32_t, uint32_t);
typedef void (*rel_t)(void);
typedef void (*cb_t)(uint32_t, uint32_t);
typedef int (*devw_t)(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
typedef int (*fset_t)(int, uint32_t);
typedef int (*fwait_t)(int, uint32_t, uint32_t, uint32_t *, int);
typedef void (*dly_t)(uint32_t);

static wr_t *W;
wr_t *fx_new(acq_t a, add_t ad, rel_t r, cb_t cb, devw_t d, fset_t fs, fwait_t fw, dly_t dl,
             const uint32_t *veneer, uint32_t block_bytes) {
    wr_fw f = { a, ad, r, cb, d, irq_off, irq_restore, fs, fw, dl };
    W = calloc(1, sizeof *W);
    wr_init(W, &f, 7, veneer, block_bytes, MISC_AT);
    return W;
}
void     fx_free(wr_t *w) { free(w); }
void     fx_installed(wr_t *w, uint32_t vol) { wr_installed(w, vol); }
int      fx_send(wr_t *w, uint32_t vol, uint32_t lr) { return wr_send(w, vol, lr); }
void     fx_cookie(wr_t *w, uint32_t f, uint32_t s) { wr_cb_cookie(w, f, s); }
uint32_t fx_acquire(wr_t *w) { return wr_cb_acquire(w); }
int      fx_add(wr_t *w, uint32_t a, uint32_t n) { return wr_cb_add(w, a, n); }
void     fx_ckpt(wr_t *w) { wr_cb_ckpt(w); }
void     fx_rb(wr_t *w) { wr_cb_rollback(w); }
void     fx_rel(wr_t *w) { wr_cb_release(w); }
void     fx_service(wr_t *w) { wr_service(w); }
void     fx_take_start(wr_t *w) { wr_take_start(w); }
int      fx_late(wr_t *w, uint32_t mgr, uint32_t node) { return wr_late_frame(w, mgr, node); }
int      fx_idle(wr_t *w) { return bq_idle(&w->q); }
uint32_t fx_counter(wr_t *w, int k) {
    const uint32_t *c = &w->n_install;
    return c[k];
}
