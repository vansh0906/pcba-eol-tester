# EOL test plan: JDB robot-joint driver board

## Device under test

48 V bus in; buck to 12 V (gate drive); LDO to 5 V (sensors); LDO to 3.3 V (MCU, also the ADC supply); 3-phase
MOSFET bridge; 2 mΩ shunt on phase A into a gain-20 current-sense amplifier offset to VDD/2; bus-voltage divider;
10 kΩ NTC with a 10 kΩ pull-up; CAN transceiver with 120 Ω termination; UART test port. Firmware 1.5.0.

## Fixture

Bed-of-nails on the board's test points (rev B: TP_48V, TP_12V, TP_5V, TP_3V3, TP_PHA, TP_CANH, TP_CANL),
programmable 48 V supply with a 0.5 A current limit, 6.5-digit DMM through a relay mux, scope with a spring ground
tip, a 10 A current source with a reference shunt, a reference temperature sensor, CAN and UART adapters.

## Sequence (config/limits.yaml)

| ID | Test | How | Released limits | Catches |
|---|---|---|---|---|
| T01 | CAN termination | ohmmeter CANH-CANL, unpowered | 108–132 Ω | missing terminator |
| T02 | Idle input current | 48 V on, 1 s settle, PSU current | 30–70 mA, **stop** | rail shorts (supply in current limit) |
| T03 | 12 V rail | DMM at TP_12V | 11.64–12.36 V | wrong buck feedback |
| T04 | 12 V ripple | scope pk-pk at TP_12V, 20 MHz BW, 16 avg | ≤ 13 mV | missing output capacitor |
| T05 | 5 V rail | DMM at TP_5V | 4.85–5.15 V | wrong LDO resistor |
| T06 | 3.3 V rail | DMM at TP_3V3 | 3.20–3.40 V | |
| T07 | Boot | firmware version over UART | "jdb-fw 1.5.0", **stop** | no crystal, unflashed |
| T08 | Bus-voltage calibration | gain = DMM(TP_48V) / firmware reading, written to flash | 0.97–1.03 | wrong divider resistor |
| T09 | Bus-voltage check | firmware − DMM after calibration | ±0.5 V | |
| T10 | Current-sense offset | firmware reading at 0 A, 64 samples | 1.60–1.70 V | wrong offset divider |
| T11 | Current-sense gain | 10 A into phase A; (V − V0) / measured current | 0.0392–0.0408 V/A | open shunt, wrong gain resistor |
| T12 | NTC | firmware temperature − reference sensor, 8 reads | ±2.0 °C | (wrong NTC: not at 25 °C, see D-02) |
| T13 | Phase A switching | 50% PWM, DMM average at TP_PHA | 22.8–25.2 V | open high-side gate |
| T14 | Switching input current | PSU current during PWM | 30–90 mA | shorted low-side FET |
| T15 | CAN | echo frame | ack + echo | transceiver not soldered |

Failures are logged and the sequence continues (full signature for diagnosis), except T02 and T07.
Every row goes to the tester log: serial, station, revision, test, value, limits, pass, time.

## Release criteria for the line

1. Every parametric test Cpk ≥ 1.33 on known-good boards, and in the pilot.
2. Gauge R&R < 10% of tolerance for every parametric test, on all three stations.
3. Every defect in the library caught 100% on 50 seeded boards, or listed with its escape rate and owner.
4. Pilot: 0 false failures; escapes only from listed defects.
5. Daily: golden unit on each station before the shift, station-to-station delta within 1/10 of tolerance.
