#ifndef FPLOSSLESS_SLOT_RUNTIME_H
#define FPLOSSLESS_SLOT_RUNTIME_H
#include "slot_capacity.h"
#define FPL_SLOT_REG_BYTES (4u + 4u * FPL_SLOT_MAX + 16u)
#define FPL_SLOT_POOL_BYTES (0x1130u + 0x1128u * FPL_SLOT_MAX)
struct fpl_slot_cookies {
    uintptr_t volume;
    uint32_t pending;
    uint32_t extra[FPL_SLOT_MAX - 128u];
};
struct fpl_slot_runtime {
    uint32_t installed, active, refused, completion_budget_us;
    uintptr_t pool_ptr;
    struct fpl_slot_plan plan;
    uint32_t registry[FPL_SLOT_REG_BYTES / 4u];
    uint32_t pool[FPL_SLOT_POOL_BYTES / 4u];
    struct fpl_slot_cookies cookies[2];
};
uint32_t fpl_slots_init(struct fpl_slot_runtime *);
uint32_t fpl_slots_prepare(struct fpl_slot_runtime *, uint32_t, uint32_t,
                           uint32_t, uint32_t, uint32_t);
uint32_t fpl_slots_bind(struct fpl_slot_runtime *, uintptr_t);
uintptr_t fpl_slots_cookie(struct fpl_slot_runtime *, uintptr_t, uint32_t);
void fpl_slots_cookie_stored(struct fpl_slot_runtime *, uintptr_t, uint32_t);
void fpl_slots_cookie_taken(struct fpl_slot_runtime *, uintptr_t, uint32_t);
#endif
