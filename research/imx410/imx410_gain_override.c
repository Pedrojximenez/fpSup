#include "imx410_gain_override.h"

int imx410_resolve_conversion_gain(int firmware_hcg,
                                   enum imx410_cg_override override_mode)
{
    if (override_mode == IMX410_CG_FORCE_LCG)
        return 0;
    if (override_mode == IMX410_CG_FORCE_HCG)
        return 1;
    return firmware_hcg != 0;
}

int imx410_resolve_high_analog(uint16_t analog_gain_code,
                              enum imx410_analog_readout_override override_mode)
{
    if (override_mode == IMX410_ANALOG_READOUT_FORCE_NORMAL)
        return 0;
    if (override_mode == IMX410_ANALOG_READOUT_FORCE_HIGH)
        return 1;
    return analog_gain_code >= IMX410_HIGH_ANALOG_GAIN_CODE;
}

struct imx410_readout_registers
imx410_make_readout_registers(int hcg, int high_analog)
{
    struct imx410_readout_registers regs;

    regs.reg_05e1 = hcg ? 1u : 0u;
    regs.reg_05e2 = high_analog ? 1u : 0u;
    regs.reg_041f = high_analog ? (hcg ? 0x1du : 0x0eu) : 0u;
    regs.reg_05a6 = hcg ? 0x2au : 0x29u;
    regs.reg_05a8 = hcg ? 0x29u : 0x27u;
    return regs;
}
