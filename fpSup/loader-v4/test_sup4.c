/* A sup for test_v4.py.  Its body starts with `struct cfg` (written by the
 * test, read and written back here), then the code.  Claims and writes rows
 * like v3/test_sup.S, registers fpSup rows, provides/finds a service, and
 * records what it was handed and where it ran. */
#include "sloader4.h"

typedef uint32_t u32;

struct cfg {
    u32 n_claims;
    struct { u32 addr, stock, kind, neww; } claims[4];
    u32 n_rows;
    struct { u32 kind; char title[20]; } rows[6];
    u32 provide_id, provide_val, find_id, release;
    /* written here */
    u32 out_svc, out_block, out_path, out_self, out_self_path, out_find;
    u32 out_uncached, out_fileis, out_pc, out_fileis_bad;
    int out_rows[6];
    u32 opened[6], toggled[6];
    struct sl_row rowmem[6];
    int out_provide;
};

static struct cfg *cfg_of(void *block) { return (struct cfg *)((uintptr_t)block + SL4_HEADER_LEN); }

static int t_open(void *arg) { (*(u32 *)arg)++; return 0; }
static int t_get(void *arg) { return (int)*(u32 *)arg; }
static int t_set(void *arg, int v) { *(u32 *)arg = (u32)v; return 0; }

int sup_entry(void *block, const struct sl_svc *svc, const char *path)
{
    struct cfg *c = cfg_of(block);
    c->out_svc = (u32)(uintptr_t)svc;
    c->out_block = (u32)(uintptr_t)block;
    c->out_path = (u32)(uintptr_t)path;
    c->out_pc = (u32)(uintptr_t)sup_entry;
    c->out_self = (u32)(uintptr_t)svc->self(svc);
    c->out_self_path = (u32)(uintptr_t)svc->self_path(svc, c);
    c->out_uncached = (u32)(uintptr_t)svc->uncached(svc, c);
    c->out_fileis = (u32)svc->file_is(svc, path, block, SL4_HEADER_LEN);
    u32 other[SL4_HEADER_LEN / 4];
    for (u32 i = 0; i < SL4_HEADER_LEN / 4; i++) other[i] = ((const u32 *)block)[i] ^ 1u;
    c->out_fileis_bad = (u32)svc->file_is(svc, path, other, SL4_HEADER_LEN);

    for (u32 i = 0; i < c->n_claims && i < 4; i++)
        if (svc->claim(svc, c->claims[i].addr, 4, &c->claims[i].stock, c->claims[i].kind) != SL_OK)
            return SL_RELEASE;
    for (u32 i = 0; i < c->n_claims && i < 4; i++)
        if (c->claims[i].neww) *(volatile u32 *)(uintptr_t)c->claims[i].addr = c->claims[i].neww;
    svc->publish(svc);

    for (u32 i = 0; i < c->n_rows && i < 6; i++) {
        struct sl_row *r = &c->rowmem[i];
        r->kind = (uint16_t)c->rows[i].kind;
        r->title = c->rows[i].title;
        r->open = t_open;
        r->get = t_get;
        r->set = t_set;
        r->arg = c->rows[i].kind == SL_ROW_TOGGLE ? (void *)&c->toggled[i] : (void *)&c->opened[i];
        c->out_rows[i] = svc->page_add(svc, r);
    }
    if (c->provide_id) c->out_provide = svc->provide(svc, c->provide_id, (void *)(uintptr_t)c->provide_val);
    if (c->find_id) c->out_find = (u32)(uintptr_t)svc->find(svc, c->find_id);
    return c->release ? SL_RELEASE : SL_KEEP;
}
