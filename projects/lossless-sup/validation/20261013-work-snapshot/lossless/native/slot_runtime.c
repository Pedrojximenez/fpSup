#include "slot_runtime.h"
static void slot_write(uintptr_t a, uint32_t word) { *(volatile uint32_t *)a = word; }
static uint32_t slot_mov16(uint32_t w, uint32_t v) {
    return (w & ~0x000f0fffu) | ((v & 0xf000u) << 4) | (v & 0xfffu);
}
#include "slot_patches.h"
static void publish(void) {
    ((void (*)(void))0xc000e91cu)();
    ((void (*)(void))0xc000eabcu)();
}
static uint32_t irq_off(void) { return ((uint32_t (*)(void))0xc000ec14u)(); }
static void irq_on(uint32_t v) { ((void (*)(uint32_t))0xc000ec24u)(v); }
static void pool_make(struct fpl_slot_runtime *s, uint32_t n) {
    uintptr_t pool = (uintptr_t)s->pool, sentinel = pool + 4u;
    s->pool[0] = 0xc0b99474u;
    s->pool[1] = pool + 0x1130u;
    s->pool[2] = pool + 0x1130u + (n - 1u) * 0x1128u;
    s->pool[0x112c / 4] = n;
    for (uint32_t i = 0; i < n; ++i) {
        uintptr_t node = pool + 0x1130u + i * 0x1128u;
        uint32_t *p = (uint32_t *)node;
        p[0] = i + 1u == n ? sentinel : node + 0x1128u;
        p[1] = i ? node - 0x1128u : sentinel;
        p[2] = 0xfafafefeu;
    }
    s->pool_ptr = pool;
    s->active = n;
}
uint32_t fpl_slots_init(struct fpl_slot_runtime *s) {
    if (!s || s->installed || !slot_sites_stock()) return 0;
    uintptr_t oldreg = ((uintptr_t (*)(void))0xc0374220u)();
    uintptr_t oldpool = *(volatile uint32_t *)0xc2f1f3d8u;
    if (oldreg != 0xc351ff44u || oldpool < 0x40000000u || (oldpool & 3u) ||
        *(volatile uint32_t *)oldpool != 0xc0b99474u) return 0;
    uint32_t mask = irq_off();
    if (*(volatile uint32_t *)(oldpool + 0x112cu) != FPL_SLOT_STOCK ||
        *(volatile uint32_t *)(oldreg + 0x18cu) || *(volatile uint8_t *)(oldreg + 0x190u)) {
        irq_on(mask); return 0;
    }
    for (uint32_t i = 0; i < FPL_SLOT_STOCK; ++i)
        if (*(volatile uint32_t *)(oldreg + 4u + 4u * i)) { irq_on(mask); return 0; }
    /* The first word is the existing mutex handle, valid for this boot.
     * Its original object stays allocated. The table/counters move together. */
    s->registry[0] = *(volatile uint32_t *)oldreg;
    for (uint32_t i = 0; i < 4; ++i)
        s->registry[1u + FPL_SLOT_MAX + i] = *(volatile uint32_t *)(oldreg + 0x184u + i * 4u);
    pool_make(s, FPL_SLOT_STOCK);
    slot_patch_layout(s);
    slot_patch_count(FPL_SLOT_STOCK);
    publish();
    s->completion_budget_us = 100000u;
    s->installed = 1;
    irq_on(mask);
    return 1;
}
uint32_t fpl_slots_prepare(struct fpl_slot_runtime *s, uint32_t w, uint32_t h,
                           uint32_t bits, uint32_t fn, uint32_t fd) {
    struct fpl_slot_plan plan;
    if (!s || !s->installed) return 0;
    if (!fpl_slot_plan(w, h, bits, 1, fn, fd, s->completion_budget_us, &plan)) {
        ++s->refused;
        return 0;
    }
    uint32_t mask = irq_off();
    uint32_t busy = s->pool[0x112c / 4] != s->active ||
                    s->registry[1 + FPL_SLOT_MAX + 2] || s->registry[1 + FPL_SLOT_MAX + 3];
    for (uint32_t i = 0; i < FPL_SLOT_MAX; ++i) busy |= s->registry[1 + i];
    for (uint32_t i = 0; i < 2; ++i)
        busy |= s->cookies[i].pending;
    if (busy) { ++s->refused; irq_on(mask); return 0; }
    s->plan = plan;
    /* The completely free native list is already usable. Unchanged capacity
     * needs neither a rebuild nor rewriting/publishing executable count sites.
     * The registry/cookie/ownership checks above apply to this path too. */
    if (s->active == plan.slots) { irq_on(mask); return 1; }
    pool_make(s, s->plan.slots);
    slot_patch_count(s->active);
    publish();
    irq_on(mask);
    return 1;
}
uint32_t fpl_slots_bind(struct fpl_slot_runtime *s, uintptr_t volume) {
    if (!s || !s->installed || !volume) return 0;
    for (uint32_t i = 0; i < 2; ++i) if (s->cookies[i].volume == volume) return 1;
    for (uint32_t i = 0; i < 2; ++i) {
        if (!s->cookies[i].pending) {
            s->cookies[i].volume = volume;
            return 1;
        }
    }
    return 0;
}
uintptr_t fpl_slots_cookie(struct fpl_slot_runtime *s, uintptr_t volume, uint32_t n) {
    if (n < 128u) return volume + 0x4854u + 4u * n;
    if (s && s->installed && n < FPL_SLOT_MAX)
        for (uint32_t i = 0; i < 2; ++i)
            if (s->cookies[i].volume == volume) return (uintptr_t)&s->cookies[i].extra[n - 128u];
    return 0; /* Caller must never admit an unbound or out-of-range cookie. */
}
/* Keep ownership locally: a completed volume can be destroyed or reused by
 * the firmware. Never dereference an old volume to decide whether it is free. */
void fpl_slots_cookie_stored(struct fpl_slot_runtime *s, uintptr_t volume, uint32_t n) {
    for (uint32_t i = 0; i < 2; ++i)
        if (s->cookies[i].volume == volume) s->cookies[i].pending = n + 1u;
}
void fpl_slots_cookie_taken(struct fpl_slot_runtime *s, uintptr_t volume, uint32_t n) {
    for (uint32_t i = 0; i < 2; ++i)
        if (s->cookies[i].volume == volume && s->cookies[i].pending == n + 1u) {
            s->cookies[i].pending = 0;
            s->cookies[i].volume = 0;
        }
}
