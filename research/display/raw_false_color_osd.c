#include "raw_false_color_osd.h"

#define ARGB_BYTES(a, r, g, b) \
    ((uint32_t)(a) | ((uint32_t)(r) << 8) | \
     ((uint32_t)(g) << 16) | ((uint32_t)(b) << 24))

static void fill_bytes(uint8_t *dst, uint8_t value, uint32_t count)
{
    while (count-- != 0)
        *dst++ = value;
}

void rfc_osd_install_palette(uint32_t palette[256])
{
    static const uint32_t colors[21] = {
        ARGB_BYTES(0xff, 0x08, 0x08, 0x18), /* -6 */
        ARGB_BYTES(0xff, 0x18, 0x18, 0x48), /* -5 */
        ARGB_BYTES(0xff, 0x20, 0x30, 0x88), /* -4 */
        ARGB_BYTES(0xff, 0x18, 0x70, 0xb8), /* -3 */
        ARGB_BYTES(0xff, 0x20, 0xb0, 0xb0), /* -2 */
        ARGB_BYTES(0xff, 0x38, 0xb8, 0x58), /* -1 */
        ARGB_BYTES(0xff, 0x70, 0x70, 0x70), /*  0 */
        ARGB_BYTES(0xff, 0xb0, 0xb8, 0x38), /* +1 */
        ARGB_BYTES(0xff, 0xe0, 0xa0, 0x28), /* +2 */
        ARGB_BYTES(0xff, 0xf0, 0x70, 0x20), /* +3 */
        ARGB_BYTES(0xff, 0xf0, 0x38, 0x30), /* +4 */
        ARGB_BYTES(0xff, 0xff, 0x18, 0x88), /* +5 */
        ARGB_BYTES(0xff, 0xff, 0xff, 0xff), /* +6 */
        ARGB_BYTES(0xff, 0xff, 0x00, 0x00), /* clip R */
        ARGB_BYTES(0xff, 0x00, 0xff, 0x00), /* clip G */
        ARGB_BYTES(0xff, 0x00, 0x00, 0xff), /* clip B */
        ARGB_BYTES(0xff, 0xff, 0xff, 0x00), /* clip RG */
        ARGB_BYTES(0xff, 0xff, 0x00, 0xff), /* clip RB */
        ARGB_BYTES(0xff, 0x00, 0xff, 0xff), /* clip GB */
        ARGB_BYTES(0xff, 0xff, 0xff, 0xff), /* clip RGB */
        ARGB_BYTES(0xff, 0x00, 0x00, 0x00), /* near black */
    };
    uint32_t i;

    if (!palette)
        return;
    for (i = 0; i < 21; ++i)
        palette[RFC_OSD_PALETTE_BASE + i] = colors[i];
}

int rfc_osd_blit_mask(const struct rfc_output *mask,
                      const struct rfc_osd_blit *blit)
{
    uint32_t mx, my, ry;
    uint32_t destination_width;
    uint32_t destination_height;

    if (!mask || !mask->palette || !blit || !blit->surface)
        return -1;
    if (mask->stride_bytes < mask->width || blit->scale_x == 0 ||
        blit->scale_y == 0 || blit->surface_stride < blit->surface_width)
        return -2;
    destination_width = mask->width * blit->scale_x;
    destination_height = mask->height * blit->scale_y;
    if (blit->destination_x + destination_width > blit->surface_width ||
        blit->destination_y + destination_height > blit->surface_height)
        return -3;

    for (my = 0; my < mask->height; ++my) {
        const uint8_t *source_row = mask->palette + my * mask->stride_bytes;
        for (ry = 0; ry < blit->scale_y; ++ry) {
            uint8_t *destination = blit->surface +
                (blit->destination_y + my * blit->scale_y + ry) *
                    blit->surface_stride + blit->destination_x;
            for (mx = 0; mx < mask->width; ++mx) {
                uint8_t zone = source_row[mx];
                uint8_t index = zone == 0 ? 0 :
                    (uint8_t)(RFC_OSD_PALETTE_BASE + zone - 1u);
                fill_bytes(destination, index, blit->scale_x);
                destination += blit->scale_x;
            }
        }
    }
    return 0;
}
