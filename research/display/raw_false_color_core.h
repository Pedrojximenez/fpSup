#ifndef SIGMA_FP_RAW_FALSE_COLOR_CORE_H
#define SIGMA_FP_RAW_FALSE_COLOR_CORE_H

#include <stddef.h>
#include <stdint.h>

enum rfc_bayer_pattern {
    RFC_RGGB = 0,
    RFC_GRBG = 1,
    RFC_GBRG = 2,
    RFC_BGGR = 3,
};

/* Firmware raw-format values used by FUN_c02da870/FUN_c0135db8. */
enum rfc_raw_format {
    RFC_RAW12 = 0,
    RFC_RAW14 = 1,
    RFC_RAW16 = 2,
    RFC_RAW10 = 3,
    RFC_RAW8 = 4,
};

enum rfc_palette_index {
    RFC_ZONE_NEG6 = 1,
    RFC_ZONE_NEG5,
    RFC_ZONE_NEG4,
    RFC_ZONE_NEG3,
    RFC_ZONE_NEG2,
    RFC_ZONE_NEG1,
    RFC_ZONE_0,
    RFC_ZONE_POS1,
    RFC_ZONE_POS2,
    RFC_ZONE_POS3,
    RFC_ZONE_POS4,
    RFC_ZONE_POS5,
    RFC_ZONE_POS6,
    RFC_CLIP_R,
    RFC_CLIP_G,
    RFC_CLIP_B,
    RFC_CLIP_RG,
    RFC_CLIP_RB,
    RFC_CLIP_GB,
    RFC_CLIP_RGB,
    RFC_NEAR_BLACK,
};

struct rfc_config {
    uint32_t width;
    uint32_t height;
    uint32_t stride_bytes;
    uint32_t tile_size;
    uint16_t black[4];
    uint16_t white[4];
    uint16_t middle_gray_green;
    uint16_t clip_margin;
    uint16_t near_black_margin;
    uint8_t bayer_pattern;
};

struct rfc_output {
    uint8_t *palette;
    uint32_t width;
    uint32_t height;
    uint32_t stride_bytes;
};

/*
 * Analyze an unpacked little-endian 16-bit Bayer view of the recording RAW.
 * Only sparse samples are read; the source buffer is never modified or copied.
 */
int rfc_analyze_u16(const uint16_t *raw, const struct rfc_config *config,
                    struct rfc_output *output);

/* Analyze the exact packed word layout decoded from FUN_c031e470..c031ea78. */
int rfc_analyze_packed(const uint32_t *raw, uint8_t format,
                       const struct rfc_config *config,
                       struct rfc_output *output);

/* Exact byte sizing used by the firmware for its non-tiled raw formats. */
uint32_t rfc_firmware_row_bytes(uint32_t width, uint8_t format);
uint32_t rfc_firmware_buffer_bytes(uint32_t width, uint32_t height,
                                   uint8_t format);

#endif
