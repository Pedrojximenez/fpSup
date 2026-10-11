#include "imx410_gain_override.h"

#include <assert.h>

int main(void)
{
    struct imx410_readout_registers r;

    assert(imx410_resolve_conversion_gain(0, IMX410_CG_AUTO) == 0);
    assert(imx410_resolve_conversion_gain(1, IMX410_CG_AUTO) == 1);
    assert(imx410_resolve_conversion_gain(0, IMX410_CG_FORCE_HCG) == 1);
    assert(imx410_resolve_conversion_gain(1, IMX410_CG_FORCE_LCG) == 0);

    assert(imx410_resolve_high_analog(0x0dfc,
           IMX410_ANALOG_READOUT_AUTO) == 0);
    assert(imx410_resolve_high_analog(0x0dfd,
           IMX410_ANALOG_READOUT_AUTO) == 1);
    assert(imx410_resolve_high_analog(0,
           IMX410_ANALOG_READOUT_FORCE_HIGH) == 1);

    r = imx410_make_readout_registers(0, 0);
    assert(r.reg_05e1 == 0 && r.reg_05e2 == 0 && r.reg_041f == 0);
    assert(r.reg_05a6 == 0x29 && r.reg_05a8 == 0x27);

    r = imx410_make_readout_registers(0, 1);
    assert(r.reg_05e1 == 0 && r.reg_05e2 == 1 && r.reg_041f == 0x0e);

    r = imx410_make_readout_registers(1, 0);
    assert(r.reg_05e1 == 1 && r.reg_05e2 == 0 && r.reg_041f == 0);
    assert(r.reg_05a6 == 0x2a && r.reg_05a8 == 0x29);

    r = imx410_make_readout_registers(1, 1);
    assert(r.reg_05e1 == 1 && r.reg_05e2 == 1 && r.reg_041f == 0x1d);
    return 0;
}
