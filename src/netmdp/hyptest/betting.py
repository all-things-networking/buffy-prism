import math
from typing import Optional

import numpy as np

from src.netmdp.hyptest.hyptest import HypTest, ErrTols, HypTestResult, HypResult, HypTestError
from src.netmdp.sampler.sampler import Sampler


class _Capital:
    """
    Test-by-betting capital process for the null "mean <= m" (direction +1) or "mean >= m" (direction -1), for
    samples in [0, upper] (Waudby-Smith & Ramdas, "Estimating means of bounded random variables by betting",
    JRSS-B 2024). K_n = prod_i (1 + d * lambda_i * (x_i - m)) with predictable lambda_i >= 0 and every factor > 0 is a
    nonnegative supermartingale under the null, so by Ville's inequality P(sup_n K_n >= 1/a) <= a: the null may be
    rejected the first time K_n >= 1/a, checked after every sample. Bets follow aGRAPA (the plug-in growth-rate
    optimal bet (mu - m) / (sigma^2 + (mu - m)^2)), truncated to c times the largest admissible bet.
    """
    def __init__(self, m: float, direction: int, upper: float, level: float, c: float = 0.75):
        self.m, self.d, self.level = m, direction, level
        self.max_bet = c / m if direction > 0 else c / (upper - m)
        self.log_k, self.log_thr = 0.0, math.log(1 / level)
        self.rejected_at: Optional[int] = None

    def bet(self, mean: float, var: float) -> float:
        edge = self.d * (mean - self.m)
        return 0.0 if edge <= 0 else min(edge / (var + edge * edge), self.max_bet)

    def scan(self, x: np.ndarray, lam: float, n0: int) -> None:
        """ Adds a block of samples bet on with the same (predictable) lam; records the first rejection. """
        if self.rejected_at is not None or lam == 0.0:
            return
        path = self.log_k + np.cumsum(np.log1p(self.d * lam * (x - self.m)))
        hit = np.flatnonzero(path >= self.log_thr)
        if hit.size:
            self.rejected_at = n0 + int(hit[0]) + 1
        self.log_k = float(path[-1])


class BettingTest(HypTest):
    """
    Sequential test of H+: p >= θ+ζ against H-: p <= θ-ζ, for the mean p of samples in [0, upper] (Bernoulli
    indicators, fixed-effort estimates, or RESTART estimates with a known bound), valid at every sample size
    (nonasymptotic and time-uniform), unlike the CLT-based Chow-Robbins sequences. It credits low variance (e.g. from
    splitting) through the bets.

    Four betting capital processes run at level a = min(α, β)/2 each:
      A: null p <= θ (rejecting it accepts H+),     B: null p >= θ (rejecting it accepts H-),
      C: null p >= θ+ζ,                             D: null p <= θ-ζ  (rejecting both stops INCONCLUSIVE).
    Wrong acceptances need A or B to reject a true null: P(accept H+ | p <= θ) <= a <= α, and likewise for H-. For
    p >= θ+ζ, failing to accept H+ needs B or C to reject a true null (<= 2a <= β); likewise for p <= θ-ζ. The test
    stops at the first decision; max_samples (if given) stops it INCONCLUSIVE.
    Bets are recomputed from the running mean and variance at the start of each block of samples (blocks grow with
    n, at most `max_block`), which keeps them predictable and the per-sample cost vectorised.
    """
    def __init__(self, theta: float, err_tols: ErrTols, indifference: float, max_samples: Optional[int] = None,
                 upper: float = 1.0, max_block: int = 1024):
        super().__init__(theta, err_tols, indifference, max_samples)
        if not 0 < theta - indifference < theta + indifference < upper:
            raise HypTestError(self.__str__() + ": need 0 < θ-ζ and θ+ζ < upper.")
        self.upper, self.max_block = upper, max_block
        self.level = min(self.get_alpha(), self.get_beta()) / 2

    def __str__(self):
        return "Betting [θ={:e}, (α,β)={}, ζ={:e}]".format(self.theta, self.err_tols, self.indifference)

    def run_test(self, sampler: Sampler) -> HypTestResult:
        self.tick()
        theta, z, up, a = self.theta, self.indifference, self.upper, self.level
        caps = {"A": _Capital(theta, +1, up, a), "B": _Capital(theta, -1, up, a),
                "C": _Capital(theta + z, -1, up, a), "D": _Capital(theta - z, +1, up, a)}
        n, total, ss, mean = 0, 0.0, 0.0, 0.0
        result = HypResult.INCONCLUSIVE
        while self.max_samples is None or n < self.max_samples:
            k = int(min(max(16, n // 8), self.max_block))
            if self.max_samples is not None:
                k = min(k, self.max_samples - n)
            x = np.fromiter((sampler.sample() for _ in range(k)), dtype=np.float64, count=k)
            if x.min() < 0 or x.max() > up:
                raise HypTestError(self.__str__() + f": a sample lies outside [0, {up}].")
            # plug-in estimates from the samples before this block, shrunk towards the null and a variance prior
            for c in caps.values():
                est = (c.m + total) / (n + 1)
                var = (up * up / 4 + ss) / (n + 1)
                c.scan(x, c.bet(est, var), n)
            first = {key: c.rejected_at for key, c in caps.items() if c.rejected_at is not None}
            decision = None
            if "A" in first or "B" in first:
                key = min((k_ for k_ in ("A", "B") if k_ in first), key=first.get)
                decision = (first[key], HypResult.ACCEPT_H_PLUS if key == "A" else HypResult.ACCEPT_H_MINUS)
            if "C" in first and "D" in first:
                stop = max(first["C"], first["D"])
                if decision is None or stop < decision[0]:
                    decision = (stop, HypResult.INCONCLUSIVE)
            used = x if decision is None else x[:decision[0] - n]
            if used.size:                                    # merge the block's mean and squared deviations (Chan)
                nb, mb = used.size, float(used.mean())
                delta = mb - mean
                ss += float(((used - mb) ** 2).sum()) + delta * delta * n * nb / (n + nb)
                mean += delta * nb / (n + nb)
                n += nb
                total += float(used.sum())
            if decision is not None:
                result = decision[1]
                break
        return HypTestResult(result, n, mean, ss / max(n, 1), self.tock())
