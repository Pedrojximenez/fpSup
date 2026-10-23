#ifndef FPLOSSLESS_SLOT_CAPACITY_H
#define FPLOSSLESS_SLOT_CAPACITY_H
#include <stdint.h>
/* Largest four-aligned capacity that keeps the relocated registry controls
 * inside native ARM LDR/STR imm12 and every runtime count in rotated imm8.
 * M12240 needs 832..852 slots at the initial 100 ms completion budget. */
#define FPL_SLOT_MAX 1016u
#define FPL_SLOT_STOCK 96u
#define FPL_SLOT_BATCH_BYTES 0x04000000u
#define FPL_SLOT_HEADER_BYTES 0x13400u
struct fpl_slot_plan {
    uint32_t file_floor, batch_frames, arrival_slots, slots, descriptor_bytes;
};
/* Two complete 64 MiB batches, arrivals during the specified completion
 * latency, four pipeline slots and two stop slots. A failed plan is not
 * permission to reduce the byte target. latency_us is a budget, not a
 * hardware guarantee. Huffman lossless JPEG requires at least one code bit
 * per sample; our DNG writer also retains the 0x13400-byte header. */
uint32_t fpl_slot_plan(uint32_t width, uint32_t height, uint32_t bits,
                       uint32_t lossless, uint32_t fps_num, uint32_t fps_den,
                       uint32_t latency_us, struct fpl_slot_plan *);
#endif
