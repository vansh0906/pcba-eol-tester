"""Test-station instruments and the board's firmware, as the tester sees them.

Each station has its own calibration errors (gain and offset), so the same board reads slightly differently on
station 1, 2 and 3; every reading also has noise. The firmware answers test commands over the UART test port:
it reports ADC readings converted to engineering units, which is where firmware choices show up in the data."""
import os

import yaml

from .board import ROOT

STATIONS = yaml.safe_load(open(os.path.join(ROOT, "config", "stations.yaml")))
ADC_BITS = 12
VREFINT = 1.212


class Station:
    def __init__(self, name, rng, cal="released", setup="released"):
        self.name, self.rng = name, rng
        c = STATIONS["stations"][name][cal]
        self.dmm_gain, self.dmm_off = c["dmm_gain_ppm"] * 1e-6, c["dmm_offset_mv"] * 1e-3
        self.isrc_gain = c["isrc_gain_ppm"] * 1e-6
        self.ohm_off = c["ohm_offset"]
        self.scope = STATIONS["ripple_setup"][setup]
        self.method = STATIONS["method"][setup]
        self.fixture_t = STATIONS["fixture_temp_c"]

    def n(self, s):
        return self.rng.normal(0, s)

    def dmm_v(self, v):
        """DC voltage at a test point: 50 ppm of reading + 0.2 mV noise."""
        return v * (1 + self.dmm_gain) + self.dmm_off + self.n(50e-6 * abs(v) + 0.2e-3)

    def ohms(self, r):
        return r + self.ohm_off + self.n(0.05) if r < 1e6 else 9.9e37   # open circuit reads overload

    def psu_current(self, i):
        return i + self.n(0.2e-3)

    def ripple_pp(self, v_pp):
        """Scope peak-to-peak. The probe setup adds pickup noise (pp) and reading scatter."""
        s = self.scope
        return (v_pp ** 2 + (s["pickup_pp_mv"] * 1e-3) ** 2) ** 0.5 + self.n(s["sigma_mv"] * 1e-3)

    def test_current(self, i_set):
        """Current the fixture's source actually delivers for a set point."""
        return i_set * (1 + self.isrc_gain)

    def dmm_i(self, i):
        """Current read by the DMM across the fixture's reference shunt (calibrated with the DMM)."""
        return i * (1 + self.dmm_gain) + self.n(20e-6 * abs(i))

    def air_temp(self):
        """Fixture air temperature for this unit (the board has soaked to it)."""
        return self.rng.uniform(*self.fixture_t)

    def ref_temp(self, t_air):
        """One reading of the fixture's reference temperature sensor (0.1 C noise)."""
        return t_air + self.n(0.1)


class Firmware:
    """What the MCU reports over the test port.
    fw 1.4.2: converts ADC codes with a fixed 3.3 V reference, one sample per reading, no calibration storage.
    fw 1.5.0: measures its real supply against the internal reference (VREFINT), averages 16 samples in test
    mode, and keeps a bus-voltage gain calibration that the tester writes at end of line."""

    def __init__(self, board, rng):
        self.b, self.rng = board, rng
        new = board.fw >= "1.5.0"
        self.vrefint_correction, self.n_avg, self.has_cal = new, (16 if new else 1), new
        self.vbus_gain = 1.0

    def version(self):
        return f"jdb-fw {self.b.fw}" if self.b.boots() else None

    def _code(self, v, n=None):
        top = 2 ** ADC_BITS - 1
        n = n or self.n_avg
        c = [max(0, min(top, round(v / self.b.vdda() * top + self.rng.normal(0, 0.7)))) for _ in range(n)]
        return sum(c) / len(c)

    def _vref(self, n=None):
        if not self.vrefint_correction:
            return 3.3
        code = self._code(VREFINT * (1 + self.b.vrefint_err), n)
        return VREFINT * (2 ** ADC_BITS - 1) / max(code, 1)

    def adc_volts(self, v, n=None):
        return self._code(v, n) * self._vref(n) / (2 ** ADC_BITS - 1)

    def bus_voltage_raw(self):
        k = 10e3 / (196e3 + 10e3)                       # nominal divider, as written in firmware
        return self.adc_volts(self.b.vbus_adc_in()) / k

    def write_vbus_cal(self, gain):
        if self.has_cal:
            self.vbus_gain = gain

    def bus_voltage(self):
        return self.bus_voltage_raw() * self.vbus_gain

    def isense_volts(self, i_phase, samples=None):
        """The test command takes a sample count (fw 1.5.0); fw 1.4.2 always returns one sample."""
        return self.adc_volts(self.b.csa_out(i_phase), samples if self.has_cal else 1)

    def temperature(self, t_true):
        import math
        v = self.adc_volts(self.b.ntc_adc_in(t_true))
        vref = self._vref()
        r = 10e3 * v / max(vref - v, 1e-6)              # nominal pull-up
        return 1 / (1 / 298.15 + math.log(r / 10e3) / 3950.0) - 273.15
