#include <stdint.h>

/* Late B2_5 hook installer.  The early Sensor Lab launcher has already copied
 * and published every handler into USER.  This installer consumes ten records
 * {site, stock, handler offset, kind} kept in its still-live staging blob.
 * All checks precede the first hook write.  Only eight-byte branch veneers
 * consume CAVE_BUMP; the menu state and handlers remain in USER. */
#define HOOK_COUNT 10u
#define CAVE_BUMP  0xC072E060u
#define CAVE_BEGIN 0xC072E064u
#define CAVE_END   0xC072EFB4u
#define ARM_VENEER 0xE51FF004u
#define THUMB_VENEER 0xF000F8DFu
#define ARM_B 0u
#define ARM_BL 1u
#define THUMB_BW 2u

#if defined(SL_UI_HOOK_HOST_TEST)
extern uint32_t slui_test_read(uintptr_t);
extern void slui_test_write(uintptr_t, uint32_t);
extern void slui_test_publish(void);
extern uint32_t slui_test_gate(const uint32_t *, uint32_t, uint32_t);
#define read32(a) slui_test_read(a)
#define write32(a, v) slui_test_write((a), (v))
#define publish() slui_test_publish()
#define gate_call(base, off, pairs, count, bound) slui_test_gate((pairs), (count), (bound))
#elif defined(__arm__) && UINTPTR_MAX == UINT32_MAX
#define read32(a) (*(volatile const uint32_t *)(a))
#define write32(a, v) (*(volatile uint32_t *)(a) = (v))
typedef uint32_t (*gate_fn)(const uint32_t *, uint32_t, uint32_t);
typedef void (*cache_fn)(void);
static void publish(void) {
    ((cache_fn)0xC000E91Cu)();
    ((cache_fn)0xC000EABCu)();
}
#define gate_call(base, off, pairs, count, bound) ((gate_fn)((base) + (off)))((pairs), (count), (bound))
#else
#error "ARM32 UI hook ABI required; host tests must explicitly substitute it"
#endif

static uint32_t arm_branch(uintptr_t site, uintptr_t veneer, uint32_t kind) {
    int32_t delta = (int32_t)(veneer - site - 8u);
    return (kind == ARM_BL ? 0xEB000000u : 0xEA000000u) | (((uint32_t)delta >> 2) & 0x00FFFFFFu);
}

static uint32_t thumb_bw(uintptr_t site, uintptr_t veneer) {
    uint32_t off = (uint32_t)(veneer - site - 4u);
    uint32_t s = (off >> 24) & 1u, i1 = (off >> 23) & 1u, i2 = (off >> 22) & 1u;
    uint32_t j1 = 1u ^ i1 ^ s, j2 = 1u ^ i2 ^ s;
    uint32_t h1 = 0xF000u | (s << 10) | ((off >> 12) & 0x3FFu);
    uint32_t h2 = 0x9000u | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7FFu);
    return h1 | (h2 << 16);
}

uint32_t sl_menu_arm(uintptr_t core_base, const uint32_t *hooks, uint32_t gate_off,
                     uint32_t journal_max) {
    uint32_t pairs[HOOK_COUNT * 2u];
    uintptr_t bump, target;
    if (!core_base || (core_base & 7u) || !hooks || !gate_off || !journal_max || journal_max > 512u)
        return 0;
    bump = read32(CAVE_BUMP);
    if ((bump & 3u) || bump < CAVE_BEGIN || bump > CAVE_END - 8u * HOOK_COUNT)
        return 0;
    for (uint32_t i = 0; i < HOOK_COUNT; ++i) {
        uintptr_t site = hooks[i * 4u], veneer = bump + 8u * i;
        uint32_t stock = hooks[i * 4u + 1u], offset = hooks[i * 4u + 2u], kind = hooks[i * 4u + 3u];
        int32_t delta = (int32_t)(veneer - site - (kind == THUMB_BW ? 4u : 8u));
        target = core_base + offset;
        if ((site & 3u) || (offset & 3u) || !offset || target < core_base ||
            kind > THUMB_BW || read32(site) != stock || (delta & 3u) ||
            (kind == THUMB_BW ? (delta < -(1 << 24) || delta >= (1 << 24)) :
             (delta < -(1 << 25) || delta >= (1 << 25)))) return 0;
        pairs[i * 2u] = site;
        pairs[i * 2u + 1u] = stock;
    }
    if (gate_call(core_base, gate_off, pairs, HOOK_COUNT, journal_max) != 1u) return 0;
    /* Publication goes before any site branch.  No fallible work remains. */
    write32(CAVE_BUMP, (uint32_t)(bump + 8u * HOOK_COUNT));
    for (uint32_t i = 0; i < HOOK_COUNT; ++i) {
        uintptr_t veneer = bump + 8u * i;
        uint32_t kind = hooks[i * 4u + 3u];
        target = core_base + hooks[i * 4u + 2u];
        write32(veneer, kind == THUMB_BW ? THUMB_VENEER : ARM_VENEER);
        write32(veneer + 4u, (uint32_t)target | (kind == THUMB_BW ? 1u : 0u));
    }
    publish();
    for (uint32_t i = 0; i < HOOK_COUNT; ++i) {
        uintptr_t site = hooks[i * 4u], veneer = bump + 8u * i;
        uint32_t kind = hooks[i * 4u + 3u];
        write32(site, kind == THUMB_BW ? thumb_bw(site, veneer) : arm_branch(site, veneer, kind));
    }
    publish();
    return 1;
}
