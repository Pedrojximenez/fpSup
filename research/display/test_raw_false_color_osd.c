#include "raw_false_color_osd.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    uint8_t mask_data[2] = {RFC_ZONE_NEG6, RFC_CLIP_RGB};
    uint8_t surface[8 * 4];
    uint32_t palette[256] = {0};
    struct rfc_output mask = {mask_data, 2, 1, 2};
    struct rfc_osd_blit blit = {surface, 8, 8, 4, 0, 1, 4, 2};

    memset(surface, 0, sizeof(surface));
    rfc_osd_install_palette(palette);
    assert(palette[195] == 0);
    assert(palette[196] != 0);
    assert(palette[216] != 0);
    assert(rfc_osd_blit_mask(&mask, &blit) == 0);
    assert(surface[8] == 196 && surface[11] == 196);
    assert(surface[12] == 215 && surface[15] == 215);
    assert(surface[16] == 196 && surface[23] == 215);
    puts("raw false-color OSD tests passed");
    return 0;
}
