#include "memory_budget.h"

#if defined(FPL_RAW_HEADROOM_HOST_TEST)
extern uint32_t fpl_headroom_read(uint32_t);
extern uint32_t fpl_headroom_mode(void);
extern uint32_t fpl_headroom_irq_off(void);
extern void fpl_headroom_irq_restore(uint32_t);
#define HR_READ(a) fpl_headroom_read(a)
#define HR_MODE() fpl_headroom_mode()
#define HR_OFF() fpl_headroom_irq_off()
#define HR_RESTORE(m) fpl_headroom_irq_restore(m)
#elif defined(__arm__) && UINTPTR_MAX == UINT32_MAX
#define HR_READ(a) (*(volatile const uint32_t *)(uintptr_t)(a))
#define HR_MODE() (((uint32_t (*)(void))0xc001cf18u)())
#define HR_OFF() (((uint32_t (*)(void))0xc000ec14u)())
#define HR_RESTORE(m) (((void (*)(uint32_t))0xc000ec24u)(m))
#else
#error "RAW counter snapshot requires ARM32 or explicit host fixtures"
#endif

uint32_t fpl_raw_headroom(void) {
    uint32_t free_bytes = UINT32_MAX, mask = HR_OFF();
    if (HR_MODE() == 3u) {
        /* C001CF78(10): class table C30739DC. C00108E0 increments
         * channel+0x18 by the allocated header span; C0010A78 subtracts it.
         * C00103A8 initializes total at +8. Read both under the same native
         * IRQ exclusion as allocator updates; do not traverse the list. */
        uint32_t p = HR_READ(0xc3073a04u);
        if (!(p & 3u) && p >= 0xc0000000u && p <= 0xc7ffffdcu && HR_READ(p) == 10u) {
            uint32_t total = HR_READ(p + 8u), used = HR_READ(p + 0x18u);
            if (total && total <= 0x40000000u && used <= total) {
                /* Conservatively leave two alignment units for sentinels
                 * and edge padding not charged in the allocation counter. */
                free_bytes = total - used;
                free_bytes = free_bytes > 2048u ? free_bytes - 2048u : 0u;
            }
        }
    }
    HR_RESTORE(mask);
    return free_bytes;
}
