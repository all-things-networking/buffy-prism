"""
Tests of the finite-sample statistics (src/netmdp/hyptest/betting.py and intervals.py):

- test_betting_errors: at p = θ (every acceptance is wrong) the betting test's wrong-acceptance rate per side stays
  below its level min(α, β)/2 (binomial upper bound), and at p >= θ+ζ it accepts H+.
- test_betting_bounded: non-Bernoulli samples in [0, upper] (scaled binomials) are accepted, samples outside are
  rejected.
- test_intervals: DKW mean intervals and Clopper-Pearson intervals cover the true value at least at their level on
  skewed bounded distributions; per_test_level is Bonferroni.

Usage: PYTHONPATH=. python tests/test_sound_statistics.py
"""
import numpy as np
from scipy.stats import binom

from src.netmdp.hyptest.betting import BettingTest
from src.netmdp.hyptest.hyptest import ErrTols, HypResult, HypTestError
from src.netmdp.hyptest.intervals import clopper_pearson, dkw_mean_ci, per_test_level
from src.netmdp.sampler.sampler import Sampler


class Draws(Sampler):
    """ Samples from draw(rng, k), buffered. """
    def __init__(self, draw, seed: int):
        super().__init__()
        self.draw, self.rng, self.buf, self.i = draw, np.random.default_rng(seed), np.empty(0), 0

    def sample(self) -> float:
        if self.i >= len(self.buf):
            self.buf, self.i = self.draw(self.rng, 65536), 0
        self.i += 1
        return float(self.buf[self.i - 1])


def bernoulli(p):
    return lambda rng, k: (rng.random(k) < p).astype(float)


def test_betting_errors():
    theta, z, reps = 0.3, 0.02, 300
    test = BettingTest(theta, ErrTols(0.05, 0.05), z)
    wrong = {HypResult.ACCEPT_H_PLUS: 0, HypResult.ACCEPT_H_MINUS: 0}
    for r in range(reps):
        res = test.run_test(Draws(bernoulli(theta), 100 + r)).result
        if res in wrong:
            wrong[res] += 1
    limit = binom.ppf(0.999, reps, test.level)       # P(count > limit) < 0.001 if the true rate is <= level
    print(f"   p = θ: wrong H+ {wrong[HypResult.ACCEPT_H_PLUS]}/{reps}, wrong H- "
          f"{wrong[HypResult.ACCEPT_H_MINUS]}/{reps} (level {test.level}, limit {limit:.0f})")
    assert max(wrong.values()) <= limit
    ok = sum(test.run_test(Draws(bernoulli(theta + 1.5 * z), 900 + r)).result == HypResult.ACCEPT_H_PLUS
             for r in range(50))
    print(f"   p = θ+1.5ζ: H+ in {ok}/50")
    assert ok >= 45


def test_betting_bounded():
    theta, z = 2.0, 0.2                                # samples in [0, 10]: binomial(10, 0.25) has mean 2.5
    test = BettingTest(theta, ErrTols(0.05, 0.05), z, upper=10.0)
    assert test.run_test(Draws(lambda rng, k: rng.binomial(10, 0.25, k), 1)).result == HypResult.ACCEPT_H_PLUS
    try:
        test.run_test(Draws(lambda rng, k: np.full(k, 11.0), 2))
    except HypTestError:
        print("   bounded samples OK")
        return
    raise AssertionError("a sample above upper was accepted")


def test_intervals():
    rng, reps, level = np.random.default_rng(5), 300, 0.95
    cover = 0
    for _ in range(reps):                              # rare large rewards: mean 0.01 * 28 = 0.28, bound 56
        x = (rng.random(3000) < 0.01) * rng.integers(0, 57, 3000)
        lo, hi = dkw_mean_ci(x, 0, 56, level)
        cover += lo <= 0.28 <= hi
    print(f"   DKW coverage {cover}/{reps} (level {level})")
    assert cover >= binom.ppf(0.001, reps, level)
    cover = 0
    for _ in range(reps):
        k = rng.binomial(2000, 0.003)
        lo, hi = clopper_pearson(int(k), 2000, level)
        cover += lo <= 0.003 <= hi
    print(f"   Clopper-Pearson coverage {cover}/{reps} (level {level})")
    assert cover >= binom.ppf(0.001, reps, level)
    assert abs(per_test_level(0.99, 4) - 0.9975) < 1e-12


if __name__ == "__main__":
    test_betting_errors()
    test_betting_bounded()
    test_intervals()
