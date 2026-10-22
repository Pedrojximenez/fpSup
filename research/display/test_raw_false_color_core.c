#include "raw_false_color_core.h"

#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

static void fill_rggb(uint16_t *raw, uint32_t width, uint32_t height,
                      uint16_t r, uint16_t g, uint16_t b)
{
    uint32_t x, y;
    for (y = 0; y < height; ++y) {
        for (x = 0; x < width; ++x) {
            if ((y & 1u) == 0 && (x & 1u) == 0)
                raw[y * width + x] = r;
            else if ((y & 1u) != 0 && (x & 1u) != 0)
                raw[y * width + x] = b;
            else
                raw[y * width + x] = g;
        }
    }
}

static void pack_msb_words(uint32_t *packed, const uint16_t *pixels,
                           uint32_t count, uint8_t bits)
{
    uint32_t i;
    memset(packed, 0, ((count * bits + 31u) >> 5) * sizeof(*packed));
    for (i = 0; i < count; ++i) {
        uint32_t bit = i * bits;
        uint32_t wi = bit >> 5;
        uint32_t shift = bit & 31u;
        uint32_t value = pixels[i] & ((1u << bits) - 1u);
        if (shift + bits <= 32u) {
            packed[wi] |= value << (32u - shift - bits);
        } else {
            uint32_t first = 32u - shift;
            packed[wi] |= value >> (bits - first);
            packed[wi + 1u] |= value << (32u - (bits - first));
        }
    }
}

int main(void)
{
    assert(rfc_firmware_row_bytes(1920, RFC_RAW12) == 2880);
    assert(rfc_firmware_row_bytes(1920, RFC_RAW14) == 3360);
    assert(rfc_firmware_row_bytes(1920, RFC_RAW16) == 3840);
    assert(rfc_firmware_row_bytes(1920, RFC_RAW10) == 2400);
    assert(rfc_firmware_row_bytes(1920, RFC_RAW8) == 1920);
    assert(rfc_firmware_buffer_bytes(1920, 1080, RFC_RAW12) == 3110400);
    assert(rfc_firmware_buffer_bytes(1919, 2, RFC_RAW12) == 5760);
    assert(rfc_firmware_buffer_bytes(0, 1080, RFC_RAW12) == 0);

    uint16_t raw[16 * 16];
    uint32_t packed[16 * 16 * 14 / 32];
    uint8_t mask[2 * 2];
    struct rfc_config config = {
        .width = 16,
        .height = 16,
        .stride_bytes = 16 * 2,
        .tile_size = 8,
        .black = {512, 512, 512, 512},
        .white = {4095, 4095, 4095, 4095},
        .middle_gray_green = 512,
        .clip_margin = 8,
        .near_black_margin = 16,
        .bayer_pattern = RFC_RGGB,
    };
    struct rfc_output output = {
        .palette = mask,
        .width = 2,
        .height = 2,
        .stride_bytes = 2,
    };

    fill_rggb(raw, 16, 16, 1024, 1024, 1024);
    memset(mask, 0, sizeof(mask));
    assert(rfc_analyze_u16(raw, &config, &output) == 0);
    assert(mask[0] == RFC_ZONE_0);

    pack_msb_words(packed, raw, 16 * 16, 14);
    config.stride_bytes = 16 * 14 / 8;
    assert(rfc_analyze_packed(packed, RFC_RAW14, &config, &output) == 0);
    assert(mask[0] == RFC_ZONE_0);
    config.stride_bytes = 16 * 2;

    fill_rggb(raw, 16, 16, 1536, 1536, 1536);
    assert(rfc_analyze_u16(raw, &config, &output) == 0);
    assert(mask[0] == RFC_ZONE_POS1);

    fill_rggb(raw, 16, 16, 4095, 1536, 1536);
    assert(rfc_analyze_u16(raw, &config, &output) == 0);
    assert(mask[0] == RFC_CLIP_R);

    fill_rggb(raw, 16, 16, 4095, 4095, 4095);
    assert(rfc_analyze_u16(raw, &config, &output) == 0);
    assert(mask[0] == RFC_CLIP_RGB);

    fill_rggb(raw, 16, 16, 512, 512, 512);
    assert(rfc_analyze_u16(raw, &config, &output) == 0);
    assert(mask[0] == RFC_NEAR_BLACK);

    puts("raw false-color core tests passed");
    return 0;
}
