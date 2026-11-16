"""Statistics a test engineer uses to set limits and qualify a tester."""
import numpy as np


def cpk(values, lo, hi):
    """Process capability against two-sided limits: distance from the mean to the nearer limit, in 3-sigma units."""
    v = np.asarray(values, float)
    m, s = v.mean(), v.std(ddof=1)
    return float(min(hi - m, m - lo) / (3 * s)) if s > 0 else float("inf")


def gauge_rr(x, lo, hi):
    """Crossed gauge R&R by two-way ANOVA (AIAG MSA), x[part, operator, trial]. Here an "operator" is a station.

    Returns standard deviations for repeatability (EV), reproducibility (AV, incl. interaction), GRR and parts (PV),
    %GRR against the tolerance (6*sigma_GRR / (hi - lo)) and against total variation, and the number of distinct
    categories (ndc)."""
    x = np.asarray(x, float)
    p, o, r = x.shape
    g = x.mean()
    mp, mo, mpo = x.mean(axis=(1, 2)), x.mean(axis=(0, 2)), x.mean(axis=2)
    ss_p = o * r * ((mp - g) ** 2).sum()
    ss_o = p * r * ((mo - g) ** 2).sum()
    ss_po = r * ((mpo - mp[:, None] - mo[None, :] + g) ** 2).sum()
    ss_e = ((x - mpo[:, :, None]) ** 2).sum()
    ms_p, ms_o = ss_p / (p - 1), ss_o / (o - 1)
    ms_po, ms_e = ss_po / ((p - 1) * (o - 1)), ss_e / (p * o * (r - 1))
    var_e = ms_e
    var_po = max((ms_po - ms_e) / r, 0.0)
    var_o = max((ms_o - ms_po) / (p * r), 0.0)
    var_p = max((ms_p - ms_po) / (o * r), 0.0)
    ev, av = var_e ** 0.5, (var_o + var_po) ** 0.5
    grr = (var_e + var_o + var_po) ** 0.5
    pv = var_p ** 0.5
    tv = (grr ** 2 + pv ** 2) ** 0.5
    return {"ev": ev, "av": av, "grr": grr, "pv": pv,
            "pct_tol": 100 * 6 * grr / (hi - lo), "pct_tv": 100 * grr / tv if tv else 0.0,
            "ndc": int(1.41 * pv / grr) if grr else 99,
            "station_means": [float(v) for v in mo]}
