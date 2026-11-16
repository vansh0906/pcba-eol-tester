"""Runs every study and writes results/: JSON per study, the pilot's tester log (CSV), report.md and docs/img/results.png.

    python run_all.py            # full run, about 30 s
    python run_all.py --quick    # smaller samples, for CI
"""
import argparse
import csv
import json
import os

import numpy as np

from eol import studies as S
from eol.sequence import PLAN, TESTS

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, "results")


def _json(name, obj):
    def conv(o):
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        raise TypeError(type(o))
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=1, default=conv)


def write_log(rows, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["serial", "station", "rev", "test", "name", "value", "lo", "hi", "pass", "time_s"])
        for r in rows:
            v = r["value"]
            w.writerow([r["serial"], r["station"], r["rev"], r["test"], r["name"],
                        f"{v:.9g}" if isinstance(v, float) else (v if v is not None else ""),
                        "" if r["lo"] is None else r["lo"], "" if r["hi"] is None else r["hi"],
                        int(bool(r["pass"])), r["time_s"]])


def plot(dft, lim, grr, pil, rip, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(2, 2, figsize=(12, 8.5))

    a = ax[0, 0]
    names = list(dft["A"]["detection"])
    y = np.arange(len(names))
    a.barh(y + 0.2, [100 * dft["A"]["detection"][d] for d in names], 0.4, label="rev A test points", color="#c9a227")
    a.barh(y - 0.2, [100 * dft["B"]["detection"][d] for d in names], 0.4, label="rev B (+TP_12V)", color="#2f6db5")
    a.set_yticks(y, names, fontsize=8); a.invert_yaxis(); a.set_xlabel("defective boards caught (%)")
    a.set_title(f"DFT: defect coverage  A {dft['A']['weighted_coverage_pct']}% -> B {dft['B']['weighted_coverage_pct']}% (rate-weighted)")
    a.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)

    a = ax[0, 1]
    tests = [t for t in grr["as found"]]
    x = np.arange(len(tests))
    a.bar(x - 0.2, [grr["as found"][t]["pct_tol"] for t in tests], 0.4, label="as found", color="#c0504d")
    a.bar(x + 0.2, [grr["released"][t]["pct_tol"] for t in tests], 0.4, label="released", color="#2f6db5")
    a.axhline(10, color="k", lw=0.8, ls="--"); a.axhline(30, color="k", lw=0.8, ls=":")
    a.set_xticks(x, [f"{t}\n{TESTS[t]['name']}" for t in tests], fontsize=6, rotation=90)
    a.set_ylabel("%GRR of tolerance"); a.set_title("Gauge R&R, 3 stations x 10 boards x 3 trials (accept < 10%)")
    a.legend(fontsize=8)

    a = ax[1, 0]
    k = list(rip["limits"])
    a.plot([float(v) for v in k], [rip["limits"][v]["escape_pct"] for v in k], "o-", label="missing-cap boards passing (escape %)", color="#c0504d")
    a.plot([float(v) for v in k], [rip["limits"][v]["false_fail_pct"] for v in k], "s-", label="good boards failing (%)", color="#2f6db5")
    a2 = a.twinx(); a2.plot([float(v) for v in k], [rip["limits"][v]["cpk"] for v in k], "^--", color="gray", label="Cpk (right axis)")
    a2.axhline(1.33, color="gray", lw=0.6, ls=":"); a2.set_ylabel("Cpk")
    a.axvline(13.0, color="k", lw=0.8); a.set_xlabel("12 V ripple upper limit (mV)"); a.set_ylabel("%")
    a.set_title("Limit setting: 12 V ripple (released at 13 mV)")
    h1, l1 = a.get_legend_handles_labels(); h2, l2 = a2.get_legend_handles_labels()
    a.legend(h1 + h2, l1 + l2, fontsize=8, loc="upper left")

    a = ax[1, 1]
    p = pil["pareto_first_fail"]
    a.bar(range(len(p)), list(p.values()), color="#2f6db5")
    a.set_xticks(range(len(p)), [f"{t}\n{TESTS[t]['name']}" for t in p], fontsize=6, rotation=90)
    a.set_ylabel("units (first failing test)")
    a.set_title(f"Pilot {pil['units']} units: FPY {pil['fpy_pct']}%, {pil['false_failures']} false fails, {pil['escapes']} escapes")
    fig.tight_layout()
    fig.savefig(path, dpi=110)


def report(dft, lim, rip, grr, pil, dia, dia_v1):
    L = []
    w = L.append
    w("# Results\n")
    w("All numbers come from `python run_all.py` on the modeled board and stations (see README).\n")
    w("## 1. DFT: what each revision's test points can catch\n")
    w("| Defect | rate (DPMU) | rev A | rev B |\n|---|---|---|---|")
    from eol.board import CFG
    for d in dft["A"]["detection"]:
        w(f"| {d} | {CFG['defects'][d]['rate']} | {100 * dft['A']['detection'][d]:.0f}% | {100 * dft['B']['detection'][d]:.0f}% |")
    for r in "AB":
        w(f"\nRev {r}: {dft[r]['defects_covered']}/{dft[r]['defects_total']} defect types always caught; "
          f"escapes {dft[r]['escape_dpmu']} DPMU; rate-weighted coverage {dft[r]['weighted_coverage_pct']}%.")
    w("\n## 2. Limits and capability (known-good boards)\n")
    a, b = lim["draft limits, fw 1.4.2"], lim["released limits, fw 1.5.0"]
    w(f"Good boards failing: draft plan {a['false_fail_pct']}% of {a['units']}, released plan {b['false_fail_pct']}% of {b['units']}.\n")
    w("| Test | draft limits | Cpk (draft, fw 1.4.2) | released limits | Cpk (released, fw 1.5.0) |\n|---|---|---|---|---|")
    for t in a["tests"]:
        x, y = a["tests"][t], b["tests"][t]
        w(f"| {t} {x['name']} | {x['lo']} .. {x['hi']} | {x['cpk']} | {y['lo']} .. {y['hi']} | {y['cpk']} |")
    w("\nBus-voltage reading error by cause (sd, and Cpk against +-0.5 V):\n")
    for k, v in lim["vbus_error_sources"].items():
        w(f"- {k}: sd {v['sd_v']} V, Cpk {v['cpk_pm_0.5V']}")
    w("\n12 V ripple limit trade-off (good boards vs boards missing an output capacitor):\n")
    w("| upper limit (mV) | good boards failing | missing-cap boards passing | Cpk |\n|---|---|---|---|")
    for k, v in rip["limits"].items():
        w(f"| {k} | {v['false_fail_pct']}% | {v['escape_pct']}% | {v['cpk']} |")
    w("\n## 3. Gauge R&R (%GRR of tolerance; accept < 10%, marginal 10-30%, reject > 30%)\n")
    w("| Test | as found | verdict | released | verdict |\n|---|---|---|---|---|")
    for t in grr["as found"]:
        x, y = grr["as found"][t], grr["released"][t]
        w(f"| {t} {x['name']} | {x['pct_tol']:.1f}% | {x['verdict']} | {y['pct_tol']:.1f}% | {y['verdict']} |")
    w("\n## 4. Pilot build (rev B, fw 1.5.0, released limits, 3 stations)\n")
    w(f"- Units {pil['units']}, defective {pil['defective']}, first-pass yield {pil['fpy_pct']}%")
    w(f"- False failures {pil['false_failures']}, escapes {pil['escapes']} ({', '.join(pil['escaped_defects']) or 'none'})")
    w(f"- Lowest Cpk of any parametric test on passing units: {pil['min_cpk']}")
    w(f"- Test time {pil['test_time_s']['passing_unit']} s per passing unit incl. 4 s handling; "
      f"{pil['uph_per_station']:.0f} units/hour per station, {pil['uph_line_3_stations']:.0f} for 3 stations")
    w(f"- First-fail Pareto: " + ", ".join(f"{k} {v}" for k, v in pil["pareto_first_fail"].items()))
    w("\n## 5. Failure diagnosis on the pilot's failing units\n")
    w(f"- v1 (z-scores clipped at 50): {dia_v1['correct']}/{dia_v1['failing_units']} ({dia_v1['accuracy_pct']}%), "
      f"confused: {dia_v1['misdiagnosed']}")
    w(f"- v2 (log-scaled z, in-limit noise ignored): {dia['correct']}/{dia['failing_units']} ({dia['accuracy_pct']}%)")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    n = 0.25 if a.quick else 1.0
    print("DFT coverage ...")
    dft = S.dft_coverage(n=int(50 * n) or 10)
    print("limit study ...")
    lim = S.limit_study(n=int(600 * n))
    rip = S.ripple_limit(n=int(300 * n))
    print("gauge R&R ...")
    grr = S.gauge_study()
    print("pilot build ...")
    rows, units = S.pilot(n=int(2000 * n))
    pil = S.pilot_summary(rows, units)
    print("failure diagnosis ...")
    dia_v1 = S.score_diagnosis(rows, units, S.build_dictionary(scale="clip"))
    dia = S.score_diagnosis(rows, units, S.build_dictionary(scale="log"))
    for name, obj in (("dft.json", dft), ("limits.json", lim), ("ripple_limit.json", rip), ("grr.json", grr),
                      ("pilot_summary.json", pil), ("diagnosis.json", {"v1_clip": dia_v1, "v2_log": dia})):
        _json(name, obj)
    write_log(rows, os.path.join(OUT, "pilot_log.csv"))
    _json("pilot_units.json", units)
    open(os.path.join(OUT, "report.md"), "w").write(report(dft, lim, rip, grr, pil, dia, dia_v1))
    plot(dft, lim, grr, pil, rip, os.path.join(ROOT, "docs", "img", "results.png"))
    print(f"\nDFT coverage: rev A {dft['A']['weighted_coverage_pct']}% -> rev B {dft['B']['weighted_coverage_pct']}% "
          f"(escapes {dft['A']['escape_dpmu']} -> {dft['B']['escape_dpmu']} DPMU)")
    print(f"Good boards failing: draft {lim['draft limits, fw 1.4.2']['false_fail_pct']}% -> released "
          f"{lim['released limits, fw 1.5.0']['false_fail_pct']}%")
    bad = [t for t, v in grr["released"].items() if v["verdict"] != "accept"]
    print(f"Gauge R&R: {sum(v['verdict'] != 'accept' for v in grr['as found'].values())} tests not accepted as found, "
          f"{len(bad)} after fixes")
    print(f"Pilot: {pil['units']} units, FPY {pil['fpy_pct']}%, false fails {pil['false_failures']}, escapes {pil['escapes']}, "
          f"min Cpk {pil['min_cpk']}, {pil['uph_line_3_stations']:.0f} UPH")
    print(f"Diagnosis: v1 {dia_v1['accuracy_pct']}% -> v2 {dia['accuracy_pct']}% of {dia['failing_units']} failing units")
    print("wrote results/ and docs/img/results.png")


if __name__ == "__main__":
    main()
