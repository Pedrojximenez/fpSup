#include "../core/qs_appearance.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    QsAppearance appearance = {7};
    unsigned previous = 0;
    for (int alpha = 0; alpha <= 15; ++alpha) {
        qs_background_set(&appearance, alpha);
        QsBackgroundPlan p = qs_background_plan(&appearance);
        assert(p.alpha4 == alpha && p.fill_passes == (alpha != 0));
        assert(p.mode == (alpha == 0 ? QS_BG_OFF : alpha == 15 ? QS_BG_OPAQUE : QS_BG_BLEND));
        unsigned percent = qs_background_percent(&appearance);
        assert(percent >= previous && percent <= 100); previous = percent;
        assert(qs_background_set(&appearance, alpha) == 0);
    }
    for (int invalid = -128; invalid < 256; ++invalid) {
        if (invalid >= 0 && invalid <= 15) continue;
        assert(qs_background_set(&appearance, invalid) == -1 && appearance.background_alpha4 == 15);
    }
    assert(qs_background_set(&appearance, 0) == 1);
    assert(qs_background_plan(&appearance).fill_passes == 0);
    assert(qs_background_percent(&appearance) == 0);
    appearance.background_alpha4 = 255;
    assert(qs_background_plan(&appearance).mode == QS_BG_OFF);
    assert(qs_background_plan(0).fill_passes == 0);
    puts("PASS: 16 alpha levels, off skips fill, opaque avoids blend, invalid values rejected");
    return 0;
}
