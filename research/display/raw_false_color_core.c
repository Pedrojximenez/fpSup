#include "raw_false_color_core.h"

enum channel { CH_R = 0, CH_G1 = 1, CH_G2 = 2, CH_B = 3 };

static enum channel channel_at(uint8_t pattern, uint32_t x, uint32_t y)
{
    static const uint8_t map[4][4] = {
        {CH_R, CH_G1, CH_G2, CH_B},
        {CH_G1, CH_R, CH_B, CH_G2},
        {CH_G1, CH_B, CH_R, CH_G2},
        {CH_B, CH_G1, CH_G2, CH_R},
    };
    return (enum channel)map[pattern & 3u][((y & 1u) << 1) | (x & 1u)];
}

static uint16_t subtract_black(uint16_t value, uint16_t black)
{
    return value > black ? (uint16_t)(value - black) : 0;
}

static uint8_t clip_palette(uint8_t mask)
{
    static const uint8_t palette[8] = {
        0, RFC_CLIP_R, RFC_CLIP_G, RFC_CLIP_RG,
        RFC_CLIP_B, RFC_CLIP_RB, RFC_CLIP_GB, RFC_CLIP_RGB,
    };
    return palette[mask & 7u];
}

static uint8_t zone_palette(uint32_t green, uint32_t middle)
{
    int zone = 0;

    if (middle == 0)
        return RFC_ZONE_0;
    if (green >= middle) {
        uint32_t threshold = middle;
        while (zone < 6 && green >= (threshold << 1)) {
            threshold <<= 1;
            ++zone;
        }
    } else {
        uint32_t threshold = middle;
        while (zone > -6 && green < ((threshold + 1u) >> 1)) {
            threshold = (threshold + 1u) >> 1;
            --zone;
        }
    }
    return (uint8_t)(RFC_ZONE_0 + zone);
}

uint32_t rfc_firmware_row_bytes(uint32_t width, uint8_t format)
{
    switch (format) {
    case RFC_RAW12:
        return (width * 3u) >> 1;
    case RFC_RAW14:
        return (width * 7u) >> 2;
    case RFC_RAW16:
        return width << 1;
    case RFC_RAW10:
        return (width * 5u) >> 2;
    case RFC_RAW8:
        return width;
    default:
        return 0;
    }
}

uint32_t rfc_firmware_buffer_bytes(uint32_t width, uint32_t height,
                                   uint8_t format)
{
    uint32_t ordinary_row;
    uint32_t final_row;
    uint32_t groups_of_12;

    if (width == 0 || height == 0)
        return 0;
    ordinary_row = (rfc_firmware_row_bytes(width, format) + 3u) & ~3u;
    /* Exact unsigned division by 12 without an ARM runtime helper. */
    groups_of_12 = (uint32_t)(((uint64_t)(width + 11u) * 0xaaaaaaabu) >> 35);
    final_row = (rfc_firmware_row_bytes(groups_of_12 * 12u,
                                        format) + 3u) & ~3u;
    if (ordinary_row == 0 || final_row == 0)
        return 0;
    return (height - 1u) * ordinary_row + final_row;
}

static uint8_t format_bits(uint8_t format)
{
    static const uint8_t bits[5] = {12, 14, 16, 10, 8};
    return format < 5 ? bits[format] : 0;
}

static uint16_t read_packed(const uint32_t *raw, uint32_t stride_bytes,
                            uint8_t bits, uint32_t x, uint32_t y)
{
    const uint32_t *row = raw + y * (stride_bytes >> 2);
    uint32_t bit = x * bits;
    uint32_t word_index = bit >> 5;
    uint32_t in_word = bit & 31u;
    uint32_t value;

    if (in_word + bits <= 32u) {
        value = row[word_index] >> (32u - in_word - bits);
    } else {
        uint32_t first = 32u - in_word;
        value = (row[word_index] & ((1u << first) - 1u)) << (bits - first);
        value |= row[word_index + 1u] >> (32u - (bits - first));
    }
    return (uint16_t)(value & ((1u << bits) - 1u));
}

static int analyze(const void *raw, int packed_format,
                   const struct rfc_config *config, struct rfc_output *output)
{
    uint32_t ox, oy;
    uint32_t source_stride;
    uint8_t bits = 16;

    if (!raw || !config || !output || !output->palette)
        return -1;
    if (config->tile_size < 2 || config->width < 2 || config->height < 2)
        return -2;
    if (packed_format < 0) {
        if (config->stride_bytes < config->width * sizeof(uint16_t))
            return -3;
    } else {
        bits = format_bits((uint8_t)packed_format);
        if (bits == 0 || (config->stride_bytes & 3u) != 0 ||
            config->stride_bytes < rfc_firmware_row_bytes(config->width,
                                                           (uint8_t)packed_format))
            return -3;
    }
    if (output->width * config->tile_size > config->width ||
        output->height * config->tile_size > config->height ||
        output->stride_bytes < output->width)
        return -4;

    source_stride = config->stride_bytes >> 1;
    for (oy = 0; oy < output->height; ++oy) {
        uint8_t *dst = output->palette + oy * output->stride_bytes;
        uint32_t sy = oy * config->tile_size;
        if (sy + 1 >= config->height)
            break;
        for (ox = 0; ox < output->width; ++ox) {
            uint16_t max_value[4] = {0, 0, 0, 0};
            uint32_t green_sum = 0;
            uint32_t green_count = 0;
            uint32_t dx, dy;
            uint8_t clipped = 0;
            uint8_t result;
            uint32_t sx = ox * config->tile_size;

            if (sx + 1 >= config->width)
                break;

            /* Four 2x2 cells cover the tile without scanning every pixel. */
            for (dy = 0; dy < 2; ++dy) {
                uint32_t py = sy + dy * (config->tile_size - 2u) + (dy != 0);
                for (dx = 0; dx < 2; ++dx) {
                    uint32_t px = sx + dx * (config->tile_size - 2u) + (dx != 0);
                    uint32_t cy, cx;
                    for (cy = 0; cy < 2; ++cy) {
                        for (cx = 0; cx < 2; ++cx) {
                            enum channel ch = channel_at(config->bayer_pattern,
                                                         px + cx, py + cy);
                            uint16_t value;
                            if (packed_format < 0) {
                                const uint16_t *raw16 = (const uint16_t *)raw;
                                value = raw16[(py + cy) * source_stride + px + cx];
                            } else {
                                value = read_packed((const uint32_t *)raw,
                                                    config->stride_bytes, bits,
                                                    px + cx, py + cy);
                            }
                            uint16_t linear = subtract_black(value, config->black[ch]);
                            if (value > max_value[ch])
                                max_value[ch] = value;
                            if (ch == CH_G1 || ch == CH_G2) {
                                green_sum += linear;
                                ++green_count;
                            }
                        }
                    }
                }
            }

            if ((uint32_t)max_value[CH_R] + config->clip_margin >= config->white[CH_R])
                clipped |= 1u;
            if ((uint32_t)max_value[CH_G1] + config->clip_margin >= config->white[CH_G1] ||
                (uint32_t)max_value[CH_G2] + config->clip_margin >= config->white[CH_G2])
                clipped |= 2u;
            if ((uint32_t)max_value[CH_B] + config->clip_margin >= config->white[CH_B])
                clipped |= 4u;

            if (clipped) {
                result = clip_palette(clipped);
            } else if (green_count == 0 ||
                       (green_sum >> 3) <= config->near_black_margin) {
                result = RFC_NEAR_BLACK;
            } else {
                /* Four sampled 2x2 cells always contain eight green sites. */
                result = zone_palette(green_sum >> 3,
                                      config->middle_gray_green);
            }
            dst[ox] = result;
        }
    }
    return 0;
}

int rfc_analyze_u16(const uint16_t *raw, const struct rfc_config *config,
                    struct rfc_output *output)
{
    return analyze(raw, -1, config, output);
}

int rfc_analyze_packed(const uint32_t *raw, uint8_t format,
                       const struct rfc_config *config,
                       struct rfc_output *output)
{
    return analyze(raw, format, config, output);
}
