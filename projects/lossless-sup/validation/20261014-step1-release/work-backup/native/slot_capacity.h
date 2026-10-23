#ifndef FPLOSSLESS_SLOT_CAPACITY_H
#define FPLOSSLESS_SLOT_CAPACITY_H
#include <stdint.h>
/* Largest four-aligned capacity that keeps the relocated registry controls
 * inside native ARM LDR/STR imm12 and every runtime count in rotated imm8.
 * M12240 needs 832..852 slots at the initial 100 ms completion budget. */
/* The largest table the relocated registry controls allow (imm12). The
 * 2026-10-13 FHD 59.94p measurements found no CPU cost from the count itself
 * (96 / 192 / 288 within 0.5 points); what bounds in-flight frames is the
 * RAW pool, not this. */
#define FPL_SLOT_MAX 1016u
#define FPL_SLOT_STOCK 96u
#define FPL_SLOT_BATCH_BYTES 0x04000000u
#define FPL_SLOT_HEADER_BYTES 0x13400u
/* MOVIE_REC_DNG (3) RAW class total, identical on every 5.02 body
 * (memmgr bufuse 708.12 MiB; HSW static 742,520,320). In-flight frames hold
 * a full RAW allocation even when their file is compressed. */
#define FPL_SLOT_RAW_POOL_BYTES 742520320u
#define FPL_SLOT_ALLOC_HEADER 0x15400u
/* Planning size of a compressed frame: 2 bits/sample. The smallest observed
 * FHD file (lens cap, 606 KB) is at this size. Smaller files do not break
 * anything: the batch closes by count (frame_limit) before 64 MiB. */
#define FPL_SLOT_LOSSLESS_BITS 2u
#define FPL_SLOT_MARGIN 6u              /* 4 pipeline/handoff + 2 stop */
struct fpl_slot_plan {
    uint32_t file_floor, batch_frames, arrival_slots, slots, descriptor_bytes;
    uint32_t ram_frames, frame_limit;
};
/* slots = min(two 64 MiB batches of planned files + arrivals during the
 * completion budget, frames the RAW pool can hold) + margin, rounded to 4,
 * within [96, FPL_SLOT_MAX]. A shortage is not a refusal: frame_limit closes
 * each batch by count so two batches plus arrivals always fit the slots.
 * The 64 MiB byte target itself is unchanged. Returns 0 only for input that
 * is unknown or out of range. latency_us is a budget, not a guarantee. */
uint32_t fpl_slot_plan(uint32_t width, uint32_t height, uint32_t bits,
                       uint32_t lossless, uint32_t fps_num, uint32_t fps_den,
                       uint32_t latency_us, struct fpl_slot_plan *);
#endif
