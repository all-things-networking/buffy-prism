import numpy as np

from src.netmdp.hyptest.adaptive_chernoff_hoeffding import AdaptiveChernoffHoeffding
from src.netmdp.hyptest.hyptest import ErrTols, HypResult
from src.netmdp.hyptest.multistage_inverse_estimator import MultistageInverseEstimator
from src.netmdp.sampler.sampler import Sampler


class BernoulliNp(Sampler):
    def __init__(self, p: float, rng: np.random.Generator):
        super().__init__()
        self.p, self.rng = p, rng

    def sample(self) -> float:
        return float(self.rng.random() < self.p)


class SplittingLike(Sampler):
    """ Non-Bernoulli [0,1] samples with mean mu: 0 w.p. 1-q, else Uniform(0, 2mu/q) (needs 2mu/q <= 1). """
    def __init__(self, mu: float, q: float, rng: np.random.Generator):
        super().__init__()
        assert 2 * mu / q <= 1
        self.mu, self.q, self.rng = mu, q, rng

    def sample(self) -> float:
        return self.rng.uniform(0, 2 * self.mu / self.q) if self.rng.random() < self.q else 0.0


def adaptive_chernoff_test(theta=0.1, zeta=0.01, alpha=0.05, beta=0.05, reps=300, seed=1):
    rng = np.random.default_rng(seed)
    test = AdaptiveChernoffHoeffding(theta, ErrTols(alpha, beta), zeta, None)
    print(f"{test}: {len(test.design.stages)} stages, worst-case n = {test.design.worst_case_samples():,}")
    for name, make in [("Bernoulli", lambda mu: BernoulliNp(mu, rng)),
                       ("splitting-like", lambda mu: SplittingLike(mu, 0.5, rng))]:
        for mu in [theta / 2, theta - zeta, theta, theta + zeta, 2 * theta]:
            res = [test.run_test(make(mu)) for _ in range(reps)]
            frac = {r: np.mean([x.get_result() == r for x in res]) for r in HypResult}
            n = np.array([x.get_n() for x in res])
            print(f"  {name:15s} mu={mu:.4f}: H+={frac[HypResult.ACCEPT_H_PLUS]:.3f} "
                  f"H-={frac[HypResult.ACCEPT_H_MINUS]:.3f} I={frac[HypResult.INCONCLUSIVE]:.3f}  "
                  f"mean n={n.mean():,.0f} max n={n.max():,}")


def multistage_estimator_test(eps=0.1, delta=0.05, reps=300, seed=2):
    rng = np.random.default_rng(seed)
    est = MultistageInverseEstimator(eps, delta)
    print(f"{est}")
    for name, make in [("Bernoulli", lambda mu: BernoulliNp(mu, rng)),
                       ("splitting-like", lambda mu: SplittingLike(mu, 0.9, rng))]:
        for mu in [0.01, 0.2, 0.45]:
            res = [est.estimate(make(mu)) for _ in range(reps)]
            miss = np.mean([abs(r.estimate - mu) >= eps * mu for r in res])
            print(f"  {name:15s} mu={mu}: miss rate={miss:.3f} (target <= {delta}) "
                  f"mean n={np.mean([r.n for r in res]):,.0f} mean stage={np.mean([r.stage for r in res]):.1f}")


if __name__ == "__main__":
    adaptive_chernoff_test()
    multistage_estimator_test()
