"""
Compares sequential tests on Bernoulli (base SMC) sample paths at the STAT 535C experiment settings:
Wald's SPRT, Chow-Robbins fixed-width (course version), Chow-Robbins with naive early stopping (re-checking the
fixed-n CI after every sample, as the course report describes), Chow-Robbins "anytime" (asymptotic confidence
sequence) and the adaptive Chernoff-Hoeffding test. Every test sees the same sample paths.

The vectorised runners replicate the classes' stopping logic exactly; check_against_classes() verifies this on a
few paths. Usage: PYTHONPATH=. python tests/sequential_test_comparison.py [reps]
"""
import math
import sys

import numpy as np
from scipy.stats import norm

from src.netmdp.hyptest.adaptive_chernoff_hoeffding import AdaptiveChernoffHoeffding
from src.netmdp.hyptest.chow_robbins import ChowRobbins
from src.netmdp.hyptest.hyptest import ErrTols, HypResult
from src.netmdp.hyptest.wald_sprt import WaldSprt
from src.netmdp.sampler.sampler import Sampler

ALPHA = BETA = 0.05
SETTINGS = [(0.70, 0.01, 0.714), (0.011, 0.001, 0.0128), (0.00015, 0.0001, 0.00041)]  # (θ, ζ, true p)


def _first(mask: np.ndarray):
    idx = np.flatnonzero(mask)
    return idx[0] if idx.size else None


def _earliest(*candidates):
    """ candidates: (index or None, decision); returns (n, decision) of the earliest, or None. """
    hits = [(i, d) for i, d in candidates if i is not None]
    return min(hits) if hits else None


def stats(x: np.ndarray):
    n = np.arange(1, len(x) + 1, dtype=np.float64)
    s = np.cumsum(x, dtype=np.float64)
    mean = s / n
    ss = np.cumsum(x * x, dtype=np.float64) - s * mean  # sum (x_i - mean_n)^2
    return n, s, mean, np.maximum(ss, 0.0)


def run_sprt(t: WaldSprt, x):
    n, s, _, _ = stats(x)
    hit = _earliest((_first(s > t.init_upper_bound + n * t.slope), '+'), (_first(s < t.init_lower_bound + n * t.slope), '-'))
    return (len(x), 'I') if hit is None else (hit[0] + 1, hit[1])


def run_cr_fixed(t: ChowRobbins, x, naive_early=False):
    n, s, mean, ss = stats(x)
    half = -t.probit_alpha * np.sqrt(ss) / n
    stop = _first((half > 0) & (half < t.eps))
    if naive_early:  # re-check the fixed-n interval after every sample (n >= 2)
        early = _earliest((_first((mean - half > t.theta) & (half > 0)), '+'), (_first((mean + half < t.theta) & (half > 0)), '-'))
        if early is not None and (stop is None or early[0] < stop):
            return early[0] + 1, early[1]
    if stop is None:
        return len(x), 'I'
    d = '+' if mean[stop] - half[stop] > t.theta else '-' if mean[stop] + half[stop] < t.theta else 'I'
    return stop + 1, d


def run_cr_anytime(t: ChowRobbins, x):
    n, s, mean, ss = stats(x)
    nonzero = np.cumsum(x != 0)
    if nonzero[min(t.n_all_zero, len(x)) - 1] == 0 and t.n_all_zero <= len(x):
        return t.n_all_zero, '-'
    with np.errstate(divide="ignore", invalid="ignore"):
        sd = np.sqrt(ss / np.maximum(n - 1, 1))
        half = sd * np.sqrt(2 * (n * t.rho2 + 1) / (n * n * t.rho2) * np.log(np.sqrt(n * t.rho2 + 1) / t.cs_alpha))
        half_minus = half * np.sqrt(np.maximum(1.0, t.theta / mean))
    ok = (nonzero >= t.min_nonzero) & (n >= 2)
    hit = _earliest((_first(ok & (mean - half > t.theta)), '+'), (_first(ok & (mean + half_minus < t.theta)), '-'),
                    (_first(ok & (np.maximum(half, half_minus) < t.indifference / 2)), 'I'))
    return (len(x), 'I') if hit is None else (hit[0] + 1, hit[1])


def run_ach(t: AdaptiveChernoffHoeffding, x):
    s = np.cumsum(x)
    best = (len(x), 'I')
    for st in t.design.stages:
        i = np.searchsorted(s, st.gamma - 1e-9)
        if st.n_plus is not None and i < len(s) and i + 1 <= st.n_plus:
            best = min(best, (i + 1, '+'))
        if st.m_minus <= len(s) and s[st.m_minus - 1] < st.gamma:
            best = min(best, (st.m_minus, '-'))
    return best


class _Replay(Sampler):
    def __init__(self, x):
        super().__init__()
        self.x, self.i = x, 0

    def sample(self):
        self.i += 1
        return float(self.x[self.i - 1])


def check_against_classes(theta=0.011, zeta=0.001, p=0.0128, paths=5, seed=3):
    rng = np.random.default_rng(seed)
    cr = ChowRobbins(theta, ErrTols(ALPHA, BETA), zeta, None)
    cr_fw = ChowRobbins(theta, ErrTols(ALPHA, BETA), zeta, None, mode="fixed_width")
    to_res = {HypResult.ACCEPT_H_PLUS: '+', HypResult.ACCEPT_H_MINUS: '-', HypResult.INCONCLUSIVE: 'I'}
    for _ in range(paths):
        x = (rng.random(2_000_000) < p).astype(np.float64)
        for test, fast in [(cr, run_cr_anytime), (cr_fw, run_cr_fixed)]:
            r = test.run_test(_Replay(x))
            assert (r.get_n(), to_res[r.get_result()]) == fast(test, x), (test.mode, r.get_n(), fast(test, x))
    print("vectorised runners match the ChowRobbins class on", paths, "paths")


def compare(reps=200, seed=7):
    rng = np.random.default_rng(seed)
    for theta, zeta, p_true in SETTINGS:
        errs = ErrTols(ALPHA, BETA)
        tests = {"SPRT": (WaldSprt(theta, errs, zeta, None), run_sprt),
                 "CR fixed-width": (ChowRobbins(theta, errs, zeta, None, mode="fixed_width"), run_cr_fixed),
                 "CR naive-early": (ChowRobbins(theta, errs, zeta, None, mode="fixed_width"),
                                    lambda t, x: run_cr_fixed(t, x, naive_early=True)),
                 "CR anytime": (ChowRobbins(theta, errs, zeta, None), run_cr_anytime),
                 "adaptive CH": (AdaptiveChernoffHoeffding(theta, errs, zeta, None), run_ach)}
        horizon = math.ceil(1.2 * max(tests["adaptive CH"][0].design.worst_case_samples(),
                                     (4 * math.sqrt(theta * (1 - theta)) / (zeta / 2)) ** 2))
        print(f"\nθ={theta} ζ={zeta}: cells = P(H+) / P(H-) / mean n over {reps} paths")
        print(f"  {'test':15s}" + "".join(f"{f'p={p:.4g}':>28s}" for p in (theta - zeta, theta, theta + zeta, p_true)))
        rows = {name: [] for name in tests}
        for p in (theta - zeta, theta, theta + zeta, p_true):
            out = {name: [] for name in tests}
            for _ in range(reps):
                x = (rng.random(horizon) < p).astype(np.float64)
                for name, (t, fn) in tests.items():
                    out[name].append(fn(t, x))
            for name, res in out.items():
                hp = np.mean([d == '+' for _, d in res]); hm = np.mean([d == '-' for _, d in res])
                rows[name].append(f"{hp:.3f}/{hm:.3f}/{np.mean([k for k, _ in res]):>9,.0f}")
        for name, cells in rows.items():
            print(f"  {name:15s}" + "".join(f"{c:>28s}" for c in cells))


if __name__ == "__main__":
    check_against_classes()
    compare(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
