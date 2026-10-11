#ifndef FP_AF_EP83_MEMORY_H
#define FP_AF_EP83_MEMORY_H
#include <stdint.h>

/* Read-only snapshot of the exact short-descriptor MMU setup used by this
 * build. Both 16-entry supersection groups are present even when identical.
 * A snapshot is a test input, NOT a live mapping lease or permission token.
 */
struct af_ep83_memory_snapshot {
    uint32_t sctlr, ttbcr, ttbr0, dacr;
    uint32_t pool, bytes, type;
    uint32_t first[16], last[16];
};

int32_t af_ep83_memory_snapshot_ok(uint32_t expected_pool,
                                  const struct af_ep83_memory_snapshot *);
int32_t af_ep83_mapping_snapshot_ok(uint32_t address, uint32_t bytes,
                                   const struct af_ep83_memory_snapshot *);
int32_t af_ep83_noncache_span_ok(uint32_t address, uint32_t bytes);
/* Actual ARM-only check: no writes to MMU/USB/allocator, no guessed alias.
 * Non-ARM builds return 0. This proves mapping+allocation descriptor, NOT the
 * exclusive owner, origin of this allocation, or lifetime against another task.
 */
int32_t af_ep83_memory_ok(uint32_t expected_pool);
int32_t af_ep83_build_identity_ok(void);
#endif
