/* Virtual RCD v2: one provider contract, independent of calculator names.
 * Calls run on the UI thread. Providers and callbacks remain resident for the
 * boot. Borrowed RCD bytes stay readable until APPLY returns; the consumer
 * copies them and never retains the producer's buffer afterwards.
 * Discovery metadata belongs to the consumer's claimed picker veneer; no new
 * loader ABI, global firmware word, or payload/AutoRun pairing is required. */
#ifndef VIRTUAL_RCD_H
#define VIRTUAL_RCD_H
#include <stdint.h>
#define VRC_MAGIC 0x31435256u
#define VRC_ABI 2u
#define VRC_PICKER 0xC043CCF8u
#define VRC_MAX_PROVIDERS 16u
#define VRC_MAX_PACKS 32u
#define VRC_ASSET_BYTES 0x400000u
enum { VRC_REGISTER=1, VRC_APPLY=2, VRC_STATUS=3, VRC_SETTINGS=4,
       VRC_RATES=5,      /* arg: struct vrc_rates *, filled: the live format's declared rates */
       VRC_RATE_SET=6 }; /* arg: rank (fps x 100) of one of them, 0 = the stock rate */
enum { VRC_OK=0, VRC_BAD_ABI=1, VRC_BAD_PROVIDER=2, VRC_FULL=3,
       VRC_BUSY=4, VRC_BUILD=5, VRC_BAD_RCD=6, VRC_RATE=7, VRC_FORMAT=8,
       VRC_NOT_READY=9, VRC_REENTER=10 };
struct vrc_input { uint32_t bytes, abi, fps_rank, format; };
struct vrc_blob { uintptr_t data; uint32_t bytes; };
typedef uint32_t (*vrc_build_fn)(uintptr_t, const struct vrc_input *, struct vrc_blob *);
/* open=0: pure readiness query, GUI parent id or 0. open=1: UI-thread
 * navigation owned by the provider, result VRC_OK or an explicit refusal. */
typedef uint32_t (*vrc_settings_fn)(uintptr_t, uint32_t open);
struct vrc_provider {
    uint32_t bytes, abi, id, capabilities;
    uintptr_t context;
    vrc_build_fn build;
    vrc_settings_fn settings;
    uint32_t reserved;
};
struct vrc_status { uint32_t bytes, abi, provider, generation, result, detail, providers, asset_bytes; };
/* The rates a format declares beyond the stock nine (RCD SEC_RATES). Each is
 * recorded while the camera's frame-rate setting holds its carrier (a stock
 * internal enum); `chosen` is the one picked (0 = the stock rate), `live` 1 while
 * the setting holds the chosen one's carrier.  The choice lives in the consumer's
 * BIN record, never in the camera's settings. */
#define VRC_MAX_RATES 8u
struct vrc_rate { uint32_t rank, num, den, carrier, nominal; };
struct vrc_rates { uint32_t bytes, abi, count, chosen, live; struct vrc_rate rate[VRC_MAX_RATES]; };
typedef uint32_t (*vrc_dispatch_fn)(uintptr_t, uint32_t, uintptr_t);
struct vrc_endpoint { uint32_t magic, abi; vrc_dispatch_fn dispatch; uintptr_t context; };
/* Only the loader's published, bounded cave arena is inspected. A stock or
 * unrelated picker never gets treated as a service pointer. */
static inline const struct vrc_endpoint *vrc_find(uintptr_t first,uintptr_t end) {
    uint32_t w=*(volatile const uint32_t *)VRC_PICKER;
    if ((w & 0xff000000u)!=0xea000000u) return 0;
    int32_t d=(int32_t)(w<<8)>>6;
    uintptr_t p=VRC_PICKER+8u+d;
    if (p<first || p+24u>end || (p&7u) ||
        *(volatile const uint32_t *)p!=0xe51ff004u) return 0;
    const struct vrc_endpoint *e=(const struct vrc_endpoint *)(p+8u);
    if (e->magic!=VRC_MAGIC || e->abi!=VRC_ABI || !e->dispatch || !e->context) return 0;
    return e;
}
#endif
