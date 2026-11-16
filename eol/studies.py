"""The studies that take a tester from first draft to production buy-off:

  dft_coverage   which assembly defects each board revision's test points can catch (DFT input to EE)
  limit_study    capability (Cpk) of each test against draft and released limits on known-good boards
  ripple_limit   the trade-off between false failures and escapes for the 12 V ripple limit
  gauge_study    gauge R&R of every parametric test across the three stations, as found and after fixes
  pilot          a 2,000-unit pilot build: yield, false failures, escapes, Pareto, Cpk, test time
  diagnose       maps a failing unit's measurements to the most likely defect, scored on the pilot failures
"""
import numpy as np

from .board import CFG, DEFECTS, VIN, Board
from .instruments import Firmware, Station
from .sequence import PLAN, TESTS, run_unit
from .stats import cpk, gauge_rr

PARAM = [t["id"] for t in PLAN if "expect" not in t]
STATIONS = ("ST1", "ST2", "ST3")


def _stations(rng, cal="released", setup="released"):
    return [Station(n, rng, cal, setup) for n in STATIONS]


def dft_coverage(seed=11, n=50):
    rng = np.random.default_rng(seed)
    sts = _stations(rng)
    out = {}
    for rev in ("A", "B"):
        det, escape_dpmu = {}, 0.0
        for d in DEFECTS:
            caught = sum(not run_unit(Board(f"{rev}-{d}-{i}", rng, rev, d), sts[i % 3], rng)[1] for i in range(n))
            det[d] = caught / n
            escape_dpmu += CFG["defects"][d]["rate"] * (1 - det[d])
        total = sum(v["rate"] for v in CFG["defects"].values())
        out[rev] = {"test_points": CFG["revisions"][rev]["test_points"], "detection": det,
                    "defects_covered": sum(v == 1.0 for v in det.values()), "defects_total": len(DEFECTS),
                    "escape_dpmu": round(escape_dpmu, 1), "weighted_coverage_pct": round(100 * (1 - escape_dpmu / total), 1)}
    return out


def _golden(rng, n, fw, limits, sts):
    vals, fails = {}, 0
    for i in range(n):
        rows, ok = run_unit(Board(f"G{i}", rng, "B", None, fw), sts[i % 3], rng, limits, fw_expect=f"jdb-fw {fw}")
        fails += not ok
        for r in rows:
            if r["test"] in PARAM:
                vals.setdefault(r["test"], []).append(r["value"])
    return vals, fails


def limit_study(seed=12, n=600):
    rng = np.random.default_rng(seed)
    sts = _stations(rng)
    res = {}
    for label, fw, limits in (("draft limits, fw 1.4.2", "1.4.2", "draft"), ("released limits, fw 1.5.0", "1.5.0", "released")):
        vals, fails = _golden(rng, n, fw, limits, sts)
        tab = {}
        for t, v in vals.items():
            lo, hi = TESTS[t][limits]
            tab[t] = {"name": TESTS[t]["name"], "lo": lo, "hi": hi, "mean": float(np.mean(v)), "sd": float(np.std(v, ddof=1)),
                      "cpk": round(cpk(v, lo, hi), 2), "out_of_limits": int(sum(not lo <= x <= hi for x in v))}
        res[label] = {"units": n, "good_units_failed": fails, "false_fail_pct": round(100 * fails / n, 2), "tests": tab}
    # L-02: where the bus-voltage error comes from (fw 1.4.2 raw, fw 1.5.0 raw, fw 1.5.0 + end-of-line cal)
    err = {"fw 1.4.2 (fixed 3.3 V ADC reference)": [], "fw 1.5.0 (VREFINT), no cal": [], "fw 1.5.0 + EOL gain cal": []}
    for i in range(n):
        st = sts[i % 3]
        for fwv, key in (("1.4.2", "fw 1.4.2 (fixed 3.3 V ADC reference)"), ("1.5.0", "fw 1.5.0 (VREFINT), no cal")):
            b = Board(f"V{i}", np.random.default_rng(1000 + i), "B", None, fwv)
            err[key].append(Firmware(b, rng).bus_voltage_raw() - VIN)
        b = Board(f"V{i}", np.random.default_rng(1000 + i), "B", None, "1.5.0")
        fw = Firmware(b, rng)
        fw.write_vbus_cal(st.dmm_v(VIN) / fw.bus_voltage_raw())
        err["fw 1.5.0 + EOL gain cal"].append(fw.bus_voltage() - st.dmm_v(VIN))
    res["vbus_error_sources"] = {k: {"sd_v": round(float(np.std(v, ddof=1)), 4), "cpk_pm_0.5V": round(cpk(v, -0.5, 0.5), 2)}
                                 for k, v in err.items()}
    return res


def ripple_limit(seed=13, n=300):
    """Good boards vs boards missing one output capacitor, as the released station measures them."""
    rng = np.random.default_rng(seed)
    sts = _stations(rng)
    good = [sts[i % 3].ripple_pp(Board(i, rng).ripple12()) * 1e3 for i in range(n)]
    bad = [sts[i % 3].ripple_pp(Board(i, rng, "B", "buck_cout_missing").ripple12()) * 1e3 for i in range(n)]
    out = {"good_mv": {"mean": float(np.mean(good)), "max": float(np.max(good))},
           "missing_cap_mv": {"mean": float(np.mean(bad)), "min": float(np.min(bad))}, "limits": {}}
    for usl in (15.0, 14.0, 13.0, 12.5, 12.0, 11.0):
        out["limits"][str(usl)] = {"false_fail_pct": round(100 * np.mean(np.array(good) > usl), 2),
                                   "escape_pct": round(100 * np.mean(np.array(bad) <= usl), 2),
                                   "cpk": round(cpk(good, 0.0, usl), 2)}
    return out


def gauge_study(seed=14, parts=10, trials=3):
    rng = np.random.default_rng(seed)
    boards = [Board(f"P{i}", np.random.default_rng(500 + i)) for i in range(parts)]
    res = {}
    for label, cal, probe in (("as found", "as_found", "as_found"), ("released", "released", "released")):
        sts = _stations(rng, cal, probe)
        x = {t: np.zeros((parts, len(sts), trials)) for t in PARAM}
        for pi, b in enumerate(boards):
            for si, st in enumerate(sts):
                for k in range(trials):
                    rows, _ = run_unit(b, st, rng)
                    for r in rows:
                        if r["test"] in x:
                            x[r["test"]][pi, si, k] = r["value"]
        tab = {}
        for t in PARAM:
            if t in ("T08",):
                continue                                  # calibration constant, not a measurement
            lo, hi = TESTS[t]["released"]
            g = gauge_rr(x[t], lo, hi)
            verdict = "accept" if g["pct_tol"] < 10 else ("marginal" if g["pct_tol"] <= 30 else "reject")
            tab[t] = {"name": TESTS[t]["name"], **{k: (round(v, 6) if isinstance(v, float) else v) for k, v in g.items()},
                      "verdict": verdict}
        res[label] = tab
    return res


def pilot(seed=15, n=2000, defect_scale=8.0):
    """Pilot build on rev B: real defect mix scaled up (early-build quality), stations round-robin."""
    rng = np.random.default_rng(seed)
    sts = _stations(rng)
    probs = np.array([CFG["defects"][d]["rate"] * defect_scale / 1e6 for d in DEFECTS])
    rows, units = [], []
    for i in range(n):
        u = rng.random()
        cum, defect = 0.0, None
        for d, p in zip(DEFECTS, probs):
            cum += p
            if u < cum:
                defect = d
                break
        b = Board(f"JDB{i:05d}", rng, "B", defect)
        st = sts[i % 3]
        r, ok = run_unit(b, st, rng)
        rows += r
        first_fail = next((x["test"] for x in r if not x["pass"]), None)
        units.append({"serial": b.serial, "station": st.name, "defect": defect, "passed": ok, "first_fail": first_fail,
                      "time_s": round(sum(x["time_s"] for x in r) + 4.0, 2)})     # + 4 s load/unload
    return rows, units


def pilot_summary(rows, units):
    n = len(units)
    good = [u for u in units if u["defect"] is None]
    bad = [u for u in units if u["defect"]]
    false_fail = [u for u in good if not u["passed"]]
    escapes = [u for u in bad if u["passed"]]
    pareto = {}
    for u in units:
        if u["first_fail"]:
            pareto[u["first_fail"]] = pareto.get(u["first_fail"], 0) + 1
    pareto = dict(sorted(pareto.items(), key=lambda kv: -kv[1]))
    passed = {u["serial"] for u in units if u["passed"]}
    cpk_tab = {}
    for t in PARAM:
        v = [r["value"] for r in rows if r["test"] == t and r["serial"] in passed]
        lo, hi = TESTS[t]["released"]
        cpk_tab[t] = {"name": TESTS[t]["name"], "n": len(v), "cpk": round(cpk(v, lo, hi), 2)}
    t_pass = np.mean([u["time_s"] for u in units if u["passed"]])
    t_all = np.mean([u["time_s"] for u in units])
    return {"units": n, "defective": len(bad), "fpy_pct": round(100 * len(passed) / n, 2),
            "false_failures": len(false_fail), "escapes": len(escapes),
            "escaped_defects": sorted({u["defect"] for u in escapes}),
            "pareto_first_fail": pareto, "cpk": cpk_tab, "min_cpk": min(v["cpk"] for v in cpk_tab.values()),
            "test_time_s": {"passing_unit": round(float(t_pass), 1), "average": round(float(t_all), 1)},
            "uph_per_station": round(3600 / float(t_all), 0), "uph_line_3_stations": round(3 * 3600 / float(t_all), 0)}


# ---- failure diagnosis ---------------------------------------------------------------------------------
def _features(rows, ref, scale="log"):
    """One number per test: how far the reading is from the golden mean, in golden standard deviations (z).
    scale="clip" (first version) clips z to +-50; scale="log" keeps the size of big deviations as
    sign(z) * log(1 + |z|), so "reads zero" and "reads half" stay different. Tests that did not run (the
    sequence stopped) and text results get fixed codes."""
    by = {r["test"]: r for r in rows}
    f = []
    for t in [p["id"] for p in PLAN]:
        r = by.get(t)
        if r is None:
            f.append(-60.0 if scale == "clip" else -12.0)
        elif t in ref:
            m, s = ref[t]
            z = (r["value"] - m) / s
            f.append(float(np.clip(z, -50, 50)) if scale == "clip" else float(np.sign(z) * np.log1p(abs(z))))
        else:
            f.append(0.0 if r["pass"] else (50.0 if scale == "clip" else 10.0))
    return np.array(f)


def build_dictionary(seed=16, n_good=300, n_each=40, scale="log"):
    """Fault dictionary: the median feature vector of each defect, from simulated defective boards."""
    rng = np.random.default_rng(seed)
    sts = _stations(rng)
    vals, _ = _golden(rng, n_good, "1.5.0", "released", sts)
    ref = {t: (float(np.mean(v)), float(np.std(v, ddof=1))) for t, v in vals.items()}
    cent = {}
    for d in DEFECTS:
        fs = []
        for i in range(n_each):
            rows, ok = run_unit(Board(f"D{i}", rng, "B", d), sts[i % 3], rng)
            if not ok:
                fs.append(_features(rows, ref, scale))
        if fs:
            cent[d] = np.median(fs, axis=0)
    return {"ref": ref, "cent": cent, "scale": scale}


def _quiet(v):
    """Zero the readings that are within 3 golden sigmas: their noise would otherwise outweigh the one test
    that tells two defects apart."""
    return np.where(np.abs(v) > np.log1p(3.0), v, 0.0)


def diagnose(rows, dic):
    f = _features(rows, dic["ref"], dic["scale"])
    if dic["scale"] == "log":
        dist = {d: float(np.abs(_quiet(f) - _quiet(c)).sum()) for d, c in dic["cent"].items()}
    else:
        dist = {d: float(np.abs(f - c).sum()) for d, c in dic["cent"].items()}
    return min(dist, key=dist.get)


def score_diagnosis(rows, units, dic):
    by = {}
    for r in rows:
        by.setdefault(r["serial"], []).append(r)
    failed = [u for u in units if not u["passed"] and u["defect"]]
    conf, right = {}, 0
    for u in failed:
        g = diagnose(by[u["serial"]], dic)
        right += g == u["defect"]
        conf.setdefault(u["defect"], {}).setdefault(g, 0)
        conf[u["defect"]][g] += 1
    wrong = {d: {g: n for g, n in v.items() if g != d} for d, v in conf.items()}
    return {"failing_units": len(failed), "correct": right, "accuracy_pct": round(100 * right / max(len(failed), 1), 1),
            "misdiagnosed": {d: v for d, v in wrong.items() if v}, "confusion": conf}
