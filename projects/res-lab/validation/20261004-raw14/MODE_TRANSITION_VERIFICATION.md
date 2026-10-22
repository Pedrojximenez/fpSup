# Sensor Lab MODE handoff: offline verification

2026-10-04. The integrated test is `projects/open-gate/build/test_sensor_lab_mode_transition.py`. Run it from that build directory with `python3 -B test_sensor_lab_mode_transition.py -v`. The run completed **16 tests, all passing**. This record concerns the source and offline models, not a camera or SD-card trial.

## What the integrated test executes

- Compiles the current production `sl_modes.c` with the `sl_menu` host fixture. The fixture simulates the Sensor Lab page, its MODE/FILTER callbacks, the GUI post queue, stock rate/bit callbacks, and navigation away from `SL_LAB` (including direct close with a NULL target).
- Runs the current ARM `imx410_fmt.S` picker and `og3krecipe.S` recipe in Unicorn against the AXIS, native bit enum, rate markers, and transition marker from each simulated handoff. The host fixture drives original setter effects; the setter firmware itself is not emulated.
- Asserts that page edits only change the selected value in memory. The outer FPS/bit setters are queued after leaving the whole Sensor Lab page. The first picker in each tested transition must produce a valid recipe, and final publication must clear phase 2 only after the target mode/rate/bit is present.
- Checks M141 and M0 from 12-bit/23.98 to RAW14/18p; M100 at 23.98; reverse M141/14-bit/18p to M123/12-bit/18p; rapid MODE reselection before exit; failed native bit commit; same FPS/bit MODE selection without redundant setter posts; direct menu close; and the 4176 × 2174 AUTO bridge with all four native bit depths (8/10/12/14) at each RAW14 rate family (18, 23.98, 24, 25, 29.97).
- A mutation run assembles the picker without the private RATE18 bridge and confirms that the M141/18p case fails. This verifies that the test observes the bridge rather than only the host model.

## High-FPS CUSTOM source scan

The test enumerates all **70 stock mode metadata entries** at seven old rate keys (`240`, `120`, `100`, `60`, `50`, `48`, `30`), four equal horizontal/vertical RWZM values (`1024`, `1280`, `1536`, `2048`), and two crop offsets (`0,0` and `32,20`). This makes 70 × 7 × 4 × 2 = **3,920 candidate 12-bit AXIS tuples**. It keeps only the **2,336** tuples for which the reference recipe solver reports a valid source mode.

For each valid source tuple it changes only the AXIS rate to 18p and then 29.97p (`30` key). The recipe solver reported a valid mode for all **4,672 target checks**; there were **zero invalid target recipes**. This supports the rate-first handoff for that sampled stock-mode/CUSTOM-geometry set. It does not exhaust every continuous zoom or crop value.

The representative real ARM path starts from **M12 at 239.76p**, RWZM **1536/1536**, crop **32,20**. For each target **M141/18p**, **M0/18p**, and **M100/29.97p**, the test checks three synchronous picker points: the old live AXIS under the newly committed carrier before `sl_menu_live`; the shared AUTO bridge before the bit setter; and the final selected AXIS after the bit setter. Every picker returns a valid recipe and `PICKOK=1`.

## Limits

This proves the modeled GUI callback order and the actual ARM picker/recipe behavior for the stated cases. The high-FPS sweep uses the Python reference solver, with representative ARM cases. No physical camera recording, sensor output, audio timing, native firmware setter execution, or card boot is established by this test. The NAV ROLE16 hook's Thumb/ABI validation is tracked separately.
