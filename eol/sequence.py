"""The end-of-line test sequence: runs every test in config/limits.yaml on one board at one station and
returns one result row per test, the way a production tester logs to its database."""
import os

import yaml

from .board import CFG, ROOT, VIN
from .instruments import Firmware

PLAN = yaml.safe_load(open(os.path.join(ROOT, "config", "limits.yaml")))["tests"]
TESTS = {t["id"]: t for t in PLAN}


def measure(tid, b, st, fw, ctx):
    """One measurement. ctx carries values between steps (e.g. the zero-current reading for T10)."""
    if tid == "T01":
        return st.ohms(b.can_term_ohms())
    if tid == "T02":
        return st.psu_current(b.i_in_idle())
    if tid == "T03":
        return st.dmm_v(b.v12())
    if tid == "T04":
        return st.ripple_pp(b.ripple12()) * 1e3
    if tid == "T05":
        return st.dmm_v(b.v5())
    if tid == "T06":
        return st.dmm_v(b.v3())
    if tid == "T07":
        return fw.version()
    if tid == "T08":
        raw, ref = fw.bus_voltage_raw(), st.dmm_v(VIN)
        gain = ref / raw if raw > 0 else 0.0
        fw.write_vbus_cal(gain)
        return gain
    if tid == "T09":
        return fw.bus_voltage() - st.dmm_v(VIN)
    if tid == "T10":
        ctx["i0"] = fw.isense_volts(0.0, st.method["isense_samples"])
        return ctx["i0"]
    if tid == "T11":
        i_set = st.method["i_test_a"]                          # injected through phase A by the fixture
        i_real = st.test_current(i_set)
        v = fw.isense_volts(i_real, st.method["isense_samples"])
        i_used = st.dmm_i(i_real) if st.method["i_measured"] else i_set
        return (v - ctx["i0"]) / i_used
    if tid == "T12":
        t_air, n = st.air_temp(), st.method["temp_reads"]
        return sum(fw.temperature(t_air) - st.ref_temp(t_air) for _ in range(n)) / n
    if tid == "T13":
        return st.dmm_v(b.phase_a_avg(0.5))
    if tid == "T14":
        return st.psu_current(b.i_in_pwm(0.5))
    if tid == "T15":
        return "ok" if b.can_echo_ok() else "no-ack"
    raise KeyError(tid)


def run_unit(board, station, rng, limits="released", fw_expect="jdb-fw 1.5.0"):
    """Returns (rows, passed). Skips tests whose test points this revision does not have."""
    tps = set(CFG["revisions"][board.rev]["test_points"])
    fw, ctx, rows, passed = Firmware(board, rng), {}, [], True
    for t in PLAN:
        if not set(t["needs"]) <= tps:
            continue
        v = measure(t["id"], board, station, fw, ctx)
        if "expect" in t:
            exp = fw_expect if t["id"] == "T07" else t["expect"]
            ok, lo, hi = v == exp, None, None
        else:
            lo, hi = t[limits]
            ok = lo <= v <= hi
        rows.append({"serial": board.serial, "station": station.name, "rev": board.rev, "test": t["id"],
                     "name": t["name"], "value": v, "lo": lo, "hi": hi, "pass": ok, "time_s": t["time_s"]})
        if not ok:
            passed = False
            if t.get("stop"):
                break
    return rows, passed
