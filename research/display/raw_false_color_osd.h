#ifndef SIGMA_FP_RAW_FALSE_COLOR_OSD_H
#define SIGMA_FP_RAW_FALSE_COLOR_OSD_H

#include <stdint.h>

#include "raw_false_color_core.h"

#define RFC_OSD_PALETTE_BASE 196u

struct rfc_osd_blit {
    uint8_t *surface;
    uint32_t surface_stride;
    uint32_t surface_width;
    uint32_t surface_height;
    uint32_t destination_x;
    uint32_t destination_y;
    uint32_t scale_x;
    uint32_t scale_y;
};

/* Preserve the camera's 0..195 false-color palette and fill unused 196..216. */
void rfc_osd_install_palette(uint32_t palette[256]);

/* Expand one palette byte per analysis tile into the indexed OSD surface. */
int rfc_osd_blit_mask(const struct rfc_output *mask,
                      const struct rfc_osd_blit *blit);

#endif
