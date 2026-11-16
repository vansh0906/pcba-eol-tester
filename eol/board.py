"""The device under test: a modeled robot-joint driver board (JDB).

A Board is one physical unit: every part value is drawn from its tolerance when the unit is built, and an
assembly defect (if any) changes the circuit the way it would on a real board. The methods return the TRUE
electrical value at a node; instruments (instruments.py) add their own error when they measure it."""
import math
import os

import numpy as np
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = yaml.safe_load(open(os.path.join(ROOT, "config", "board.yaml")))
DEFECTS = list(CFG["defects"])
VIN = 48.0          # fixture bus supply
PSU_ILIM = 0.5      # fixture supply current limit, A
T0 = 298.15


class Board:
    def __init__(self, serial, rng, rev="B", defect=None, fw="1.5.0"):
        assert defect is None or defect in CFG["defects"], defect
        self.serial, self.rev, self.defect, self.fw = serial, rev, defect, fw
        self.p = {}
        for k, (nom, tol) in CFG["parts"].items():
            nom, tol = float(nom), float(tol)
            self.p[k] = nom * (1 + rng.normal(0, tol / 3)) if tol else nom
        self.p["csa_vos"] = rng.normal(0, CFG["csa_vos_sigma"])
        self.vrefint_err = rng.normal(0, 0.001)      # MCU internal reference after factory trim
        d, p = defect, self.p
        if d == "buck_fb_wrong":
            p["buck_rbot"] = 12.1e3 * (1 + rng.normal(0, 0.01 / 3))
        if d == "buck_cout_missing":
            p["buck_c"] /= 2; p["buck_esr"] *= 2
        if d == "ldo5_r_wrong":
            p["ldo5_r2"] = 12.1e3 * (1 + rng.normal(0, 0.01 / 3))
        if d == "csa_gain_wrong":
            p["csa_gain"] = 10.0 * (1 + rng.normal(0, 0.005 / 3))
        if d == "csa_offset_wrong":
            p["csa_offset_div"] = 0.400
        if d == "ntc_wrong_part":
            p["ntc_beta"] = 3435.0 * (1 + rng.normal(0, 0.01 / 3))
        if d == "vbus_div_wrong":
            p["vbus_r1"] = 182e3 * (1 + rng.normal(0, 0.01 / 3))

    # ---- power -----------------------------------------------------------------------------------
    def shorted_rail(self):
        return self.defect == "short_3v3_gnd"

    def v12(self, i_load=0.15):
        if self.shorted_rail():
            return 0.0
        p = self.p
        return p["buck_vref"] * (1 + p["buck_rtop"] / p["buck_rbot"]) - p["buck_droop"] * i_load

    def ripple12(self):
        """Peak-to-peak output ripple of the buck, from inductor ripple current and the output cap."""
        if self.shorted_rail():
            return 0.0
        p, v = self.p, self.v12()
        d = v / VIN
        di = (VIN - v) * d / (p["buck_l"] * p["buck_fsw"])
        return di * (p["buck_esr"] + 1 / (8 * p["buck_fsw"] * p["buck_c"]))

    def v5(self):
        if self.shorted_rail():
            return 0.0
        p = self.p
        return min(p["ldo5_vref"] * (1 + p["ldo5_r1"] / p["ldo5_r2"]), self.v12() - 0.3)

    def v3(self):
        if self.shorted_rail():
            return 0.0
        p = self.p
        return min(p["ldo3_vref"] * (1 + p["ldo3_r1"] / p["ldo3_r2"]), self.v5() - 0.25)

    def i_in_idle(self):
        """Input current at 48 V with the bridge off. A rail short pulls the supply into its current limit."""
        if self.shorted_rail():
            return PSU_ILIM
        return self.p["iq_board"]

    # ---- MCU and firmware-visible signals --------------------------------------------------------
    def boots(self):
        return self.defect != "mcu_xtal_missing" and not self.shorted_rail()

    def vdda(self):
        return self.v3()

    def vbus_adc_in(self, vbus=VIN):
        p = self.p
        return vbus * p["vbus_r2"] / (p["vbus_r1"] + p["vbus_r2"])

    def csa_out(self, i_phase):
        p = self.p
        if self.defect == "shunt_open":
            i_phase = 0.0                      # no current can flow through an open shunt
        return p["csa_offset_div"] * self.v3() + p["csa_gain"] * (p["shunt"] * i_phase + p["csa_vos"])

    def ntc_adc_in(self, t_c):
        p = self.p
        r = p["ntc_r25"] * math.exp(p["ntc_beta"] * (1 / (t_c + 273.15) - 1 / T0))
        return self.v3() * r / (r + p["ntc_pullup"])

    # ---- bridge ----------------------------------------------------------------------------------
    def phase_a_avg(self, duty=0.5):
        """Average phase-A voltage while the bridge switches phase A at the given duty (no load)."""
        if self.defect == "ls_fet_short":
            return PSU_ILIM * self.p["fet_rds"]            # shoot-through: supply in current limit
        if self.defect == "hs_gate_open":
            return 0.0                                     # high side never turns on
        return duty * VIN

    def i_in_pwm(self, duty=0.5):
        if self.defect == "ls_fet_short":
            return PSU_ILIM
        return self.p["iq_board"] + 0.012                  # gate-drive charge at 20 kHz

    # ---- CAN -------------------------------------------------------------------------------------
    def can_term_ohms(self):
        return 1e9 if self.defect == "can_term_missing" else self.p["can_term"]

    def can_echo_ok(self):
        return self.boots() and self.defect != "can_xcvr_open"


def make_rng(seed):
    return np.random.default_rng(seed)
