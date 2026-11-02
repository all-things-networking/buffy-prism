"""
Fixed-sample confidence intervals with finite-sample guarantees (no CLT), as recommended for statistical model
checking by Budde, Hartmanns, Meggendorfer, Weininger & Wienhöft, "Sound statistical model checking for
probabilities and expected rewards", TACAS 2025:
  - clopper_pearson: exact binomial interval for a probability;
  - dkw_mean_ci: interval for the mean of samples known to lie in [lower, upper] (e.g. a reward summed over k steps,
    bounded by k times the largest per-step reward), from the Dvoretzky-Kiefer-Wolfowitz-Massart band on the CDF;
  - per_test_level: the per-interval level for a family of intervals reported together (Bonferroni).
"""
import math

import numpy as np
from scipy.stats import beta


def clopper_pearson(successes: int, n: int, level: float = 0.99) -> tuple[float, float]:
    """ Two-sided exact interval for a binomial proportion. """
    a = 1 - level
    lo = 0.0 if successes == 0 else float(beta.ppf(a / 2, successes, n - successes + 1))
    hi = 1.0 if successes == n else float(beta.ppf(1 - a / 2, successes + 1, n - successes))
    return lo, hi


def dkw_mean_ci(x: np.ndarray, lower: float, upper: float, level: float = 0.99) -> tuple[float, float]:
    """
    Two-sided interval for E[X] from iid samples x of X in [lower, upper]. With probability >= level the true CDF lies
    within eps = sqrt(log(2/(1-level))/(2n)) of the empirical one (DKW with Massart's constant), so the mean lies
    between the means of the two extreme CDFs in the band: moving mass eps from the largest samples to `lower`, and
    from the smallest samples to `upper`.
    """
    x = np.sort(np.asarray(x, dtype=np.float64))
    n = len(x)
    if n == 0 or x[0] < lower or x[-1] > upper:
        raise ValueError(f"need samples within [{lower}, {upper}]")
    eps = math.sqrt(math.log(2 / (1 - level)) / (2 * n))
    if eps >= 1:
        return lower, upper
    w = np.full(n, 1.0 / n)

    def trimmed(xs: np.ndarray) -> float:
        """ sum of xs weighted 1/n each after removing mass eps from the start of xs """
        cut = np.minimum(np.cumsum(w), eps) - np.minimum(np.cumsum(w) - w, eps)
        return float(((w - cut) * xs).sum())
    lo = eps * lower + trimmed(x[::-1])
    hi = eps * upper + trimmed(x)
    return lo, hi


def per_test_level(level: float, m: int) -> float:
    """ Level for each of m intervals (or tests) so that all hold together with probability >= level. """
    return 1 - (1 - level) / m
