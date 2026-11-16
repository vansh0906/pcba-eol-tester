# Results

All numbers come from `python run_all.py` on the modeled board and stations (see README).

## 1. DFT: what each revision's test points can catch

| Defect | rate (DPMU) | rev A | rev B |
|---|---|---|---|
| short_3v3_gnd | 600 | 100% | 100% |
| buck_fb_wrong | 300 | 0% | 100% |
| buck_cout_missing | 500 | 0% | 100% |
| ldo5_r_wrong | 300 | 100% | 100% |
| shunt_open | 400 | 100% | 100% |
| csa_gain_wrong | 200 | 100% | 100% |
| csa_offset_wrong | 200 | 100% | 100% |
| hs_gate_open | 500 | 100% | 100% |
| ls_fet_short | 250 | 100% | 100% |
| ntc_wrong_part | 300 | 0% | 0% |
| can_term_missing | 400 | 100% | 100% |
| can_xcvr_open | 500 | 100% | 100% |
| vbus_div_wrong | 200 | 100% | 100% |
| mcu_xtal_missing | 350 | 100% | 100% |

Rev A: 11/14 defect types always caught; escapes 1100.0 DPMU; rate-weighted coverage 78.0%.

Rev B: 13/14 defect types always caught; escapes 300.0 DPMU; rate-weighted coverage 94.0%.

## 2. Limits and capability (known-good boards)

Good boards failing: draft plan 22.83% of 600, released plan 0.0% of 600.

| Test | draft limits | Cpk (draft, fw 1.4.2) | released limits | Cpk (released, fw 1.5.0) |
|---|---|---|---|---|
| T01 can_term_ohm | 108.0 .. 132.0 | 9.64 | 108.0 .. 132.0 | 10.92 |
| T02 idle_current_a | 0.03 .. 0.07 | 3.23 | 0.03 .. 0.07 | 3.25 |
| T03 rail_12v | 11.64 .. 12.36 | 1.79 | 11.64 .. 12.36 | 1.72 |
| T04 ripple_12v_mv | 0.0 .. 15.0 | 2.48 | 0.0 .. 13.0 | 1.75 |
| T05 rail_5v | 4.85 .. 5.15 | 1.52 | 4.85 .. 5.15 | 1.58 |
| T06 rail_3v3 | 3.25 .. 3.35 | 0.66 | 3.2 .. 3.4 | 1.56 |
| T08 vbus_cal_gain | 0.97 .. 1.03 | 1.16 | 0.97 .. 1.03 | 2.21 |
| T09 vbus_err_v | -0.5 .. 0.5 | 0.29 | -0.5 .. 0.5 | 15.76 |
| T10 isense_offset_v | 1.6 .. 1.7 | 4.86 | 1.6 .. 1.7 | 1.46 |
| T11 isense_gain_vpa | 0.0394 .. 0.0406 | 0.51 | 0.0392 .. 0.0408 | 1.7 |
| T12 ntc_err_c | -2.0 .. 2.0 | 5.92 | -2.0 .. 2.0 | 6.0 |
| T13 pha_avg_v | 22.8 .. 25.2 | 259.58 | 22.8 .. 25.2 | 249.44 |
| T14 pwm_current_a | 0.03 .. 0.09 | 5.74 | 0.03 .. 0.09 | 5.86 |

Bus-voltage reading error by cause (sd, and Cpk against +-0.5 V):

- fw 1.4.2 (fixed 3.3 V ADC reference): sd 0.3611 V, Cpk 0.31
- fw 1.5.0 (VREFINT), no cal: sd 0.2248 V, Cpk 0.73
- fw 1.5.0 + EOL gain cal: sd 0.0101 V, Cpk 16.44

12 V ripple limit trade-off (good boards vs boards missing an output capacitor):

| upper limit (mV) | good boards failing | missing-cap boards passing | Cpk |
|---|---|---|---|
| 15.0 | 0.0% | 3.33% | 2.43 |
| 14.0 | 0.0% | 1.67% | 2.03 |
| 13.0 | 0.0% | 0.67% | 1.64 |
| 12.5 | 0.0% | 0.33% | 1.44 |
| 12.0 | 0.0% | 0.0% | 1.25 |
| 11.0 | 1.33% | 0.0% | 0.85 |

## 3. Gauge R&R (%GRR of tolerance; accept < 10%, marginal 10-30%, reject > 30%)

| Test | as found | verdict | released | verdict |
|---|---|---|---|---|
| T01 can_term_ohm | 1.3% | accept | 1.4% | accept |
| T02 idle_current_a | 3.1% | accept | 2.6% | accept |
| T03 rail_12v | 14.3% | marginal | 0.8% | accept |
| T04 ripple_12v_mv | 54.6% | reject | 7.3% | accept |
| T05 rail_5v | 14.2% | marginal | 1.0% | accept |
| T06 rail_3v3 | 14.2% | marginal | 1.1% | accept |
| T09 vbus_err_v | 5.7% | accept | 5.8% | accept |
| T10 isense_offset_v | 1.6% | accept | 0.8% | accept |
| T11 isense_gain_vpa | 28.4% | marginal | 7.9% | accept |
| T12 ntc_err_c | 16.1% | marginal | 5.5% | accept |
| T13 pha_avg_v | 8.8% | accept | 0.4% | accept |
| T14 pwm_current_a | 2.2% | accept | 2.2% | accept |

## 4. Pilot build (rev B, fw 1.5.0, released limits, 3 stations)

- Units 2000, defective 78, first-pass yield 96.4%
- False failures 0, escapes 6 (ntc_wrong_part)
- Lowest Cpk of any parametric test on passing units: 1.45
- Test time 14.8 s per passing unit incl. 4 s handling; 244 units/hour per station, 732 for 3 stations
- First-fail Pareto: T13 10, T05 10, T02 10, T15 7, T04 7, T11 7, T01 6, T08 4, T07 4, T10 4, T03 3

## 5. Failure diagnosis on the pilot's failing units

- v1 (z-scores clipped at 50): 67/72 (93.1%), confused: {'shunt_open': {'csa_gain_wrong': 4}, 'csa_gain_wrong': {'shunt_open': 1}}
- v2 (log-scaled z, in-limit noise ignored): 72/72 (100.0%)
