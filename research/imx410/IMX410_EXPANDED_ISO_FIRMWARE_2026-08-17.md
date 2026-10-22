# SIGMA fp expanded ISO firmware implementation

Firmware: SIGMA fp 5.02

## Result

- Expanded ISO 6, 12, 25, and 50 all clamp to the exact same internal gain
  request as ISO 100. They do not select lower sensor analog gain.
- ISO 51200 and 102400 are real entries in the ISO-to-relative-gain table, but
  the gain allocator caps the sensor analog stage and sends the excess to the
  four-channel ISP digital-gain path. They do not create additional sensor
  sensitivity or shadow information.

## ISO conversion table

`FUN_c00b8b40` returns the table descriptor at `0xc0746728`. It contains 11
ISO/relative-gain pairs:

| ISO | Relative gain |
|---:|---:|
| 100 | 117 |
| 200 | 234 |
| 400 | 468 |
| 800 | 936 |
| 1600 | 1872 |
| 3200 | 3744 |
| 6400 | 7488 |
| 12800 | 14976 |
| 25600 | 29952 |
| 51200 | 59904 |
| 102400 | 119808 |

`FUN_c00b8a38`, reached through `FUN_c00b8860`, converts ISO to relative gain.
For an input below the first ISO node it returns the second value of the first
pair without extrapolation. Consequently all ISO values below 100 become
relative gain 117, exactly the ISO 100 request.

## Sensor and digital gain split

`FUN_c03131e0` dispatches the relative-gain request to
`XC_ImageSensorIMX410::v8` (`0xc0323580`). This routine returns a packed value:

- low 16 bits: sensor analog-gain code;
- high 16 bits: digital-gain multiplier.

The IMX410 configuration limits the analog portion to 30 dB. Above that point
the routine holds the analog portion at its limit and increases the digital
multiplier. `FUN_c0312f18` then:

1. sends the low 16-bit value through `XC_ImageSensorIMX410::v11` to the sensor;
2. sends the high 16-bit value through `FUN_c0313340` to the four-channel ISP
   gain functions `FUN_c0634508` and `FUN_c06345e8`.

The sensor analog code is ultimately written to IMX410 registers `0x003d` to
`0x0040` by `XC_ImageSensorIMX410::v10` (`0xc0323818`).

## Interpretation

Low expanded ISO is a pull/exposure-index implementation: the sensor readout
gain is ISO 100, while metering, processing, or metadata represents the lower
ISO selection. It cannot increase full well or highlight headroom in RAW.

High expanded ISO performs additional digital amplification after the analog
stage. It changes output code values, but is reproducible by multiplying a
lower-ISO RAW during development and cannot improve signal-to-noise ratio.

The physically meaningful gain choices remain the normal ISO range and the
conversion-gain transition used for the camera's dual-base-ISO behavior.
