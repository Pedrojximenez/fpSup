/* fp 5.02 read-only mapping guard. See EP83_MEMORY_MAPPING_2026-09-16.md. */
#include "af_ep83_memory.h"
#include <stddef.h>

#define LEASE_END 0x65000u
#define POOL_ALLOC 0x100000u
#define TABLE_BASE 0x44300000u
#define TABLE_CONTROL 0x44300040u
#define NC_SUPERSECTION 0x00044c02u

static int32_t registers_ok(const struct af_ep83_memory_snapshot *s) {
    /* MMU enabled; reject TEX remap and big-endian tables. TTBCR must select
     * the full short-descriptor TTBR0 table (no N split, PD0/PD1, or LPAE).
     * Boot C000E7B0 loads exactly this TTBR and DACR; other layouts fail closed.
     */
    return (s->sctlr & ((1u << 28) | (1u << 25) | 1u)) == 1u &&
           s->ttbcr == 0 && s->ttbr0 == TABLE_CONTROL &&
           s->dacr == 0x55555555u;
}

int32_t af_ep83_mapping_snapshot_ok(uint32_t address, uint32_t bytes,
                                   const struct af_ep83_memory_snapshot *s) {
    if (!s || !registers_ok(s) || !bytes || bytes > POOL_ALLOC ||
        address < 0x40000000u || address > 0x80000000u - bytes) return 0;
    uint32_t first = (address & 0xff000000u) | NC_SUPERSECTION;
    uint32_t last = ((address + bytes - 1u) & 0xff000000u) | NC_SUPERSECTION;
    for (uint32_t i = 0; i < 16; ++i)
        if (s->first[i] != first || s->last[i] != last) return 0;
    return 1;
}

int32_t af_ep83_memory_snapshot_ok(uint32_t pool,
                                  const struct af_ep83_memory_snapshot *s) {
    if (!s || pool < 0x40000000u || pool > 0x80000000u - POOL_ALLOC ||
        (pool & 63u) || s->pool != pool || s->bytes < POOL_ALLOC ||
        s->bytes > 0x80000000u - pool || s->type != 0) return 0;
    return af_ep83_mapping_snapshot_ok(pool, LEASE_END, s);
}

int32_t af_ep83_build_identity_ok(void) {
#if defined(__arm__)
    const volatile uint32_t *p = (const volatile uint32_t *)(uintptr_t)0xc0725f94u;
    return p[0] == 0x61613331u && p[1] == 0x30313236u && p[2] == 0x66653036u &&
           p[3] == 0x31316666u && p[4] == 0x61626161u && p[5] == 0x31326239u &&
           p[6] == 0x32396461u && p[7] == 0x35303035u && p[8] == 0x36323033u &&
           p[9] == 0x66633530u &&
           *(const volatile uint8_t *)(uintptr_t)0xc0725fbcu == 0;
#else
    return 0;
#endif
}

#if defined(__arm__)
static void memory_registers(struct af_ep83_memory_snapshot *s) {
    __asm__ volatile("mrc p15, 0, %0, c1, c0, 0" : "=r" (s->sctlr));
    __asm__ volatile("mrc p15, 0, %0, c2, c0, 2" : "=r" (s->ttbcr));
    __asm__ volatile("mrc p15, 0, %0, c2, c0, 0" : "=r" (s->ttbr0));
    __asm__ volatile("mrc p15, 0, %0, c3, c0, 0" : "=r" (s->dacr));
}

static void memory_table(uint32_t address, uint32_t bytes,
                          struct af_ep83_memory_snapshot *s) {
    __asm__ volatile("dsb sy" ::: "memory");
    const volatile uint32_t *table = (const volatile uint32_t *)(uintptr_t)TABLE_BASE;
    uint32_t first = (address >> 20) & ~15u;
    uint32_t last = ((address + bytes - 1u) >> 20) & ~15u;
    for (uint32_t i = 0; i < 16; ++i) {
        s->first[i] = table[first+i];
        s->last[i] = table[last+i];
    }
}
#endif

int32_t af_ep83_memory_ok(uint32_t pool) {
#if defined(__arm__)
    struct af_ep83_memory_snapshot s;
    memory_registers(&s);
    if (!registers_ok(&s) || pool < 0x40000000u ||
        pool > 0x80000000u - POOL_ALLOC || (pool & 63u)) return 0;
    const volatile uint32_t *allocation = (const volatile uint32_t *)(uintptr_t)0xc3757a7cu;
    s.pool = allocation[0]; s.bytes = allocation[1]; s.type = allocation[2];
    memory_table(pool, LEASE_END, &s);
    return af_ep83_memory_snapshot_ok(pool, &s);
#else
    (void)pool;
    return 0;
#endif
}

int32_t af_ep83_noncache_span_ok(uint32_t address, uint32_t bytes) {
#if defined(__arm__)
    struct af_ep83_memory_snapshot s;
    memory_registers(&s);
    if (!registers_ok(&s) || !bytes || bytes > POOL_ALLOC ||
        address < 0x40000000u || address > 0x80000000u - bytes) return 0;
    memory_table(address, bytes, &s);
    return af_ep83_mapping_snapshot_ok(address, bytes, &s);
#else
    (void)address; (void)bytes;
    return 0;
#endif
}
