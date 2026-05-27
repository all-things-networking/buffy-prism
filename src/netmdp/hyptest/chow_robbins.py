import numpy as np
from scipy.stats import norm

from src.netmdp.hyptest.hyptest import HypTest, ErrTols, HypTestResult, HypResult, HypTestError
from src.netmdp.sampler.sampler import Sampler


def update_sample_ests(sample: float, mean: float, ss: float, n: int) -> tuple[float, float]:
    """" Welford's Online Algorithm for sample mean and variance """
    delta1 = sample - mean
    mean += delta1 / n
    delta2 = sample - mean
    ss += delta1 * delta2 # (ss / n) is the new (biased) sample variance
    return mean, ss


class ChowRobbins(HypTest):
    """" Chow-Robbins Sequential Gaussian CI test """
    def __init__(self, theta: float, err_tols: ErrTols, indifference: float, max_samples: int):
        super().__init__(theta, err_tols, indifference, max_samples)
        if theta - indifference <= 0 or theta + indifference >= 1:
            raise HypTestError(self.__str__() + ": [θ-ζ, θ+ζ] must lie in (0,1).")
        self.probit_alpha = norm.ppf(self.get_alpha())
        self.eps = indifference / (1+(norm.ppf(self.get_beta())/self.probit_alpha))

    def __str__(self):
        return "Chow-Robbins [θ={:e}, (α,β)={}, ζ={:e}]".format(self.theta, self.err_tols, self.indifference)

    def run_test(self, sampler: Sampler) -> HypTestResult:
        result = HypResult.INCONCLUSIVE
        self.tick()
        x = sampler.sample()
        p_hat = x  # (online) sample mean
        ss_x = 0 # sum from 1 to n of (X_i - p_hat)^2; divide by n to get (biased) sample var
        n = 1
        while True:
            n += 1
            x = sampler.sample()
            p_hat, ss_x = update_sample_ests(x, p_hat, ss_x, n)
            # Half-width of CI; Phi^{-1}(α) * sqrt(Var(p_hat)) where Var(p_hat) is (sample var / n), or (ss_x / n^2)
            half_ci = -1 * self.probit_alpha * np.sqrt(ss_x) / n
            if n % 500 == 0:
                print(f"n: {n}, p_hat: {p_hat:.6f}, half CI: {half_ci:.6f}, eps: {self.eps}")
            if 0 < half_ci < self.eps:
                break
        if (p_hat - half_ci) > self.theta:
            result = HypResult.ACCEPT_H_PLUS
        elif (p_hat + half_ci) < self.theta:
            result = HypResult.ACCEPT_H_MINUS
        wall_time = self.tock()
        return HypTestResult(result, n, p_hat, (ss_x / n), wall_time)