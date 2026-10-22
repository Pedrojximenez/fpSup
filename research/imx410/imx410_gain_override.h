#ifndef SIGMA_FP_IMX410_GAIN_OVERRIDE_H
#define SIGMA_FP_IMX410_GAIN_OVERRIDE_H

#include <stdint.h>

enum imx410_cg_override {
    IMX410_CG_AUTO = 0,
    IMX410_CG_FORCE_LCG,
    IMX410_CG_FORCE_HCG,
};

enum imx410_analog_readout_override {
    IMX410_ANALOG_READOUT_AUTO = 0,
    IMX410_ANALOG_READOUT_FORCE_NORMAL,
    IMX410_ANALOG_READOUT_FORCE_HIGH,
};

struct imx410_gain_override {
    enum imx410_cg_override conversion_gain;
    enum imx410_analog_readout_override analog_readout;
};

struct imx410_readout_registers {
    uint8_t reg_05e1;
    uint8_t reg_05e2;
    uint8_t reg_041f;
    uint8_t reg_05a6;
    uint8_t reg_05a8;
};

/* Firmware 5.02 switches the high-analog configuration at this gain code. */
#define IMX410_HIGH_ANALOG_GAIN_CODE 0x0dfdu

int imx410_resolve_conversion_gain(int firmware_hcg,
                                   enum imx410_cg_override override_mode);
int imx410_resolve_high_analog(uint16_t analog_gain_code,
                              enum imx410_analog_readout_override override_mode);
struct imx410_readout_registers
imx410_make_readout_registers(int hcg, int high_analog);

#endif
