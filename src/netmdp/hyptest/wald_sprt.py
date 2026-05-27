import numpy as np

from src.netmdp.hyptest.hyptest import HypTest, ErrTols, HypTestResult, HypTestError, HypResult
from src.netmdp.sampler.sampler import Sampler


class WaldSprt(HypTest):
    """" Wald's SPRT (one-sided, Bernoulli trials) """
    def __init__(self, theta: float, err_tols: ErrTols, indifference: float, max_samples: int):
        super().__init__(theta, err_tols, indifference, max_samples)
        if theta - indifference <= 0 or theta + indifference >= 1:
            raise HypTestError(self.__str__() + ": [θ-𝛿, θ+𝛿] must lie in (0,1).")
        self.slope, self.init_upper_bound, self.init_lower_bound = self.compute_sprt_params()

    def __str__(self):
        return "Wald's SPRT [θ={:e}, (α,β)={}, 𝛿={:e}]".format(self.theta, self.err_tols, self.indifference)

    def log_thresholds(self):
        upper = (1 - self.get_beta()) / self.get_alpha()
        lower = self.get_beta() / (1 - self.get_alpha())
        return np.log(upper), np.log(lower)

    def compute_sprt_params(self):
        p0 = self.theta - self.indifference
        p1 = self.theta + self.indifference
        log_upper, log_lower = self.log_thresholds()
        den = np.log( p1 / p0 ) - np.log( (1-p1) / (1-p0) )
        slope = np.log( (1-p0) / (1-p1) ) / den
        init_upper_bound = log_upper / den
        init_lower_bound = log_lower / den
        return slope, init_upper_bound, init_lower_bound

    def run_test(self, sampler: Sampler) -> HypTestResult:
        result = HypResult.INCONCLUSIVE
        sn = 0
        n = 0
        upper_bound = self.init_upper_bound
        lower_bound = self.init_lower_bound
        slope = self.slope
        self.tick()
        while True: #n < self.max_samples:
            n += 1
            upper_bound += slope
            lower_bound += slope
            sn += sampler.sample() # ASSUME BERNOULLI SAMPLE
            if n % 10000 == 0:
                print(f"n: {n}, p_hat: {sn / n:.6f}, upper_bound: {upper_bound/n:.6f}, lower_bound: {lower_bound/n:.6f}")
            if sn > upper_bound:
                result = HypResult.ACCEPT_H_PLUS
                break
            if sn < lower_bound:
                result = HypResult.ACCEPT_H_MINUS
                break
        wall_time = self.tock()
        sample_mean = sn / n
        sample_var = sample_mean * (1 - sample_mean)
        return HypTestResult(result, n, sample_mean, sample_var, wall_time)