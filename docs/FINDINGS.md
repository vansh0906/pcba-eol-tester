# Findings

What each study found, what was changed, and who it went to. Numbers are from `python run_all.py`
(seeded, so they reproduce exactly).

## DFT (to electronics design)

| ID | Finding | Evidence | Action |
|---|---|---|---|
| D-01 | **Rev A cannot see the 12 V gate-drive rail.** A wrong buck feedback resistor (rail at 10.1 V) and a missing output capacitor (ripple doubles) pass every rev A test: the 5 V and 3.3 V LDOs still regulate, so nothing downstream moves. | 0% of both defects caught on rev A; together 800 of the 1,100 DPMU that escape. | Requested **TP_12V with an adjacent GND pad** (also needed for a short ripple ground loop, G-01). Rev B: both caught 100%; rate-weighted coverage **78.0% → 94.0%**, escapes **1,100 → 300 DPMU**. |
| D-02 | **A wrong-beta NTC is invisible at EOL.** The 3435 and 3950 parts are both 10 kΩ at 25 °C; at 28 °C the reading is off by only 0.4 °C. | 0% caught on both revisions; all 6 pilot escapes are this defect. | Not testable without a temperature step (+60 s). Sent to SMT: reel-ID verification at the feeder and AOI part-marking check. Kept on the escape list (300 DPMU). |

## Limits (to EE and firmware)

| ID | Finding | Evidence | Action |
|---|---|---|---|
| L-01 | **3.3 V rail limit tighter than the design can hold.** Draft ±1.5% from the spec; LDO reference ±1.5% plus 1% feedback resistors stack to about ±1.8% (3σ), and the nominal is 3.288 V. | Cpk **0.66**, 13 of 600 good boards outside the draft limit. | Released **3.20–3.40 V (±3%)**, inside the MCU's 3.0–3.6 V: Cpk **1.56**. Recommended to EE instead of moving to 0.1% resistors. |
| L-02 | **Bus-voltage reading error had two causes.** fw 1.4.2 converts ADC codes with a fixed 3.3 V reference (the rail is ±1.8%), and the 1% divider adds about ±1.4%. | sd 0.36 V, Cpk **0.31** against ±0.5 V; 124 of 600 good boards out. | Firmware **1.5.0 measures VREFINT** first (Cpk 0.73), and the tester now **calibrates each unit**: T08 writes gain = DMM / firmware to flash, T09 verifies. Cpk **16.4**. T08's 0.97–1.03 window still catches a wrong divider resistor (gain 1.07). |
| L-03 | **Current-sense gain** limit ±1.5% with single-sample ADC readings and the same fixed reference. | Cpk **0.51**, 45 of 600 good boards out. | VREFINT (fw 1.5.0), averaged readings (G-03) and **±2%** (shunt 1% + amplifier 0.5% stack): Cpk **1.70**. |
| L-04 | **12 V ripple limit trades escapes for false fails.** At the draft 15 mV, 3.3% of boards missing an output cap pass. | Sweep in `results/ripple_limit.json`: 13 mV → 0.67% escape, Cpk 1.64; 12 mV → 0% escape but Cpk 1.25. | Released **13 mV** (Cpk above 1.33); the residual missing-cap escape is covered by AOI, which sees a missing capacitor directly. |

## Gauge R&R and station correlation (tester qualification)

10 known-good boards x 3 stations x 3 trials, crossed ANOVA; accept below 10% of tolerance.

| ID | Finding | As found | Fix | Released |
|---|---|---|---|---|
| G-01 | Ripple repeatability: 10x probe with a 15 cm ground lead picks up switching noise; single-shot peak-to-peak. | **54.6% reject** | Spring ground tip on the new TP_12V/GND pair, 20 MHz bandwidth limit, 16 averages | **7.3%** |
| G-02 | All three rails marginal, dominated by reproducibility: station 2 reads **0.25% high** (12.016 V vs 11.987 V on the same boards). Its DMM was past its calibration date. | **14.2–14.3%** | Recalibrated; station-to-station check added to the daily golden-unit run | **0.8–1.1%** |
| G-03 | Current-sense gain: ADC noise over a 0.2 V signal at 5 A, and the tester divided by the *set* current while the stations' sources differ by up to 350 ppm. | **28.4%** | 10 A test current, 64-sample firmware average, divide by the current read on the fixture's reference shunt | **7.9%** |
| G-04 | NTC check: one reading of the fixture reference sensor (0.1 °C noise) against a ±2 °C window. | **16.1%** | Average 8 readings | **5.5%** |

## Pilot build and buy-off

| ID | Result |
|---|---|
| P-01 | 2,000 units of rev B with fw 1.5.0, defect rates 8x the assumed line rate (early-build quality), stations round-robin. **FPY 96.4%**, **0 false failures**, **6 escapes** (all D-02), lowest Cpk of any parametric test **1.45**. |
| P-02 | **14.8 s** per passing unit including 4 s load/unload: **244 units/hour per station, 732 for three**. Short and boot failures stop early (safety, and nothing after them can run). |
| P-03 | Rust `tlog` and the Python summary agree on the same tester log: yield, first-fail Pareto, Cpk of every test (checked in CI). |

## Failure diagnosis (to the repair bench)

| ID | Finding | Fix |
|---|---|---|
| F-01 | The first fault dictionary scored **93.1%** (67/72) on the pilot's failing units: it **confused an open shunt with a wrong gain resistor**. Both read far below the gain limit, and clipping z-scores at 50 made "reads zero" and "reads half" identical; the noise in passing tests then decided. | Log-scaled deviations and in-limit readings ignored: **100%** (72/72), and 100% on three other pilot seeds. |
