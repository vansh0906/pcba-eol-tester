"""Checks that gate CI: the board model, the tester's behaviour, the statistics and the studies' key results."""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from eol import studies as S                      # noqa: E402
from eol.board import DEFECTS, VIN, Board         # noqa: E402
from eol.instruments import Firmware, Station     # noqa: E402
from eol.sequence import run_unit                 # noqa: E402
from eol.stats import cpk, gauge_rr               # noqa: E402


def stations(rng, cal="released", setup="released"):
    return [Station(n, rng, cal, setup) for n in ("ST1", "ST2", "ST3")]


def test_nominal_board_values():
    b = Board("N", np.random.default_rng(0))
    for k in b.p:                                  # put every part at nominal
        b.p[k] = Board.__init__.__globals__["CFG"]["parts"].get(k, [b.p[k]])[0]
        b.p[k] = float(b.p[k])
    b.p["csa_vos"] = 0.0
    assert b.v12(0.0) == pytest.approx(12.0, abs=1e-9)
    assert b.v5() == pytest.approx(4.992, abs=1e-6)
    assert b.v3() == pytest.approx(3.288, abs=1e-6)
    assert b.csa_out(5.0) - b.csa_out(0.0) == pytest.approx(0.2, abs=1e-9)
    assert 8e-3 < b.ripple12() < 10e-3


def test_good_boards_pass_released_plan():
    rng = np.random.default_rng(1)
    sts = stations(rng)
    fails = sum(not run_unit(Board(i, rng), sts[i % 3], rng)[1] for i in range(150))
    assert fails == 0


def test_rev_b_catches_every_defect_but_the_ntc_and_rev_a_misses_three():
    rng = np.random.default_rng(2)
    sts = stations(rng)
    for d in DEFECTS:
        caught_b = sum(not run_unit(Board(i, rng, "B", d), sts[i % 3], rng)[1] for i in range(12))
        caught_a = sum(not run_unit(Board(i, rng, "A", d), sts[i % 3], rng)[1] for i in range(12))
        if d == "ntc_wrong_part":
            assert caught_a == caught_b == 0
        elif d in ("buck_fb_wrong", "buck_cout_missing"):
            assert (caught_a, caught_b) == (0, 12), d
        else:
            assert caught_a == caught_b == 12, d


def test_sequence_stops_on_a_rail_short_and_skips_missing_test_points():
    rng = np.random.default_rng(3)
    st = Station("ST1", rng)
    rows, ok = run_unit(Board("S", rng, "B", "short_3v3_gnd"), st, rng)
    assert not ok and [r["test"] for r in rows] == ["T01", "T02"]
    rows, ok = run_unit(Board("A", rng, "A"), st, rng)
    assert ok and "T03" not in [r["test"] for r in rows] and "T04" not in [r["test"] for r in rows]


def test_vrefint_and_eol_calibration_shrink_the_bus_voltage_error():
    rng = np.random.default_rng(4)
    st = Station("ST1", rng)
    e142, e150, ecal = [], [], []
    for i in range(200):
        e142.append(Firmware(Board(i, np.random.default_rng(i), "B", None, "1.4.2"), rng).bus_voltage_raw() - VIN)
        fw = Firmware(Board(i, np.random.default_rng(i), "B", None, "1.5.0"), rng)
        e150.append(fw.bus_voltage_raw() - VIN)
        fw.write_vbus_cal(st.dmm_v(VIN) / fw.bus_voltage_raw())
        ecal.append(fw.bus_voltage() - VIN)
    assert np.std(e142) > 1.4 * np.std(e150) > 10 * np.std(ecal)


def test_cpk():
    v = np.random.default_rng(5).normal(10.0, 1.0, 20000)
    assert cpk(v, 4.0, 16.0) == pytest.approx(2.0, abs=0.05)
    assert cpk(v, 7.0, 20.0) == pytest.approx(1.0, abs=0.03)


def test_gauge_rr_recovers_known_components():
    rng = np.random.default_rng(6)
    parts, ops, trials = 30, 3, 4
    part = rng.normal(0, 1.0, parts)
    op = np.array([-0.3, 0.0, 0.3])
    x = part[:, None, None] + op[None, :, None] + rng.normal(0, 0.2, (parts, ops, trials))
    g = gauge_rr(x, -6, 6)
    assert g["ev"] == pytest.approx(0.2, rel=0.15)
    assert g["av"] == pytest.approx(0.3, rel=0.35)
    assert g["pv"] == pytest.approx(1.0, rel=0.3)


def test_gauge_study_rejects_as_found_and_accepts_released():
    g = S.gauge_study(parts=6, trials=3)
    assert g["as found"]["T04"]["verdict"] == "reject"
    assert all(v["verdict"] == "accept" for v in g["released"].values())


def test_pilot_and_diagnosis():
    rows, units = S.pilot(n=600)
    s = S.pilot_summary(rows, units)
    assert s["false_failures"] == 0
    assert set(s["escaped_defects"]) <= {"ntc_wrong_part"}
    assert s["min_cpk"] >= 1.33
    d = S.score_diagnosis(rows, units, S.build_dictionary(n_good=150, n_each=20))
    assert d["accuracy_pct"] == 100.0


@pytest.mark.skipif(shutil.which("cargo") is None, reason="Rust toolchain not installed")
def test_rust_tlog_matches_python(tmp_path):
    from run_all import write_log
    rows, units = S.pilot(n=300)
    log = tmp_path / "log.csv"
    write_log(rows, log)
    out = subprocess.run(["cargo", "run", "-q", "--release", "--manifest-path", os.path.join(ROOT, "tools", "tlog", "Cargo.toml"),
                          "--", str(log)], capture_output=True, text=True, check=True).stdout
    r = json.loads(out)
    p = S.pilot_summary(rows, units)
    assert r["units"] == p["units"] and r["fpy_pct"] == pytest.approx(p["fpy_pct"], abs=0.005)
    assert r["pareto_first_fail"] == p["pareto_first_fail"]
    for t, v in p["cpk"].items():
        assert r["tests"][t]["n"] == v["n"]
        assert r["tests"][t]["cpk"] == pytest.approx(v["cpk"], abs=0.006)
