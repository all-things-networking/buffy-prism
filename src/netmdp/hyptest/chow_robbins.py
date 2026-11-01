import math
from typing import Optional

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


def mixture_cs_half_width(sd: float, n: int, rho2: float, alpha: float) -> float:
    """
    Half-width of the two-sided Gaussian-mixture asymptotic confidence sequence (Robbins' normal mixture boundary;
    Waudby-Smith, Arnold, Wu & Ramdas, "Time-uniform central limit theory and asymptotic confidence sequences",
    Ann. Statist. 2024): mean_n +/- sd_n sqrt(2(n rho^2 + 1)/(n^2 rho^2) log(sqrt(n rho^2 + 1)/alpha)).
    It covers the mean at ALL n simultaneously with probability -> 1-alpha, so it may be checked after every sample.
    """
    return sd * math.sqrt(2 * (n * rho2 + 1) / (n * n * rho2) * math.log(math.sqrt(n * rho2 + 1) / alpha))


class ChowRobbins(HypTest):
    """"
    Chow-Robbins sequential Gaussian CI test.

    mode="fixed_width" (the STAT 535C version): sample until the half-width of the (1-2α) CLT interval for the mean
    is below eps = ζ/(1+Φ⁻¹(β)/Φ⁻¹(α)), then accept H+/H- if the interval excludes θ, else INCONCLUSIVE. It never
    stops early, so it always uses about Φ⁻¹(α)² σ²/eps² samples.

    mode="anytime" (default): decide as soon as an asymptotic confidence sequence (mixture_cs_half_width, level
    α' = min(α, β)) excludes θ, and stop INCONCLUSIVE once its half-width is below ζ/2. Because the sequence is
    time-uniform, checking it after every sample does not inflate the error (unlike re-checking a fixed-n CI, which
    does). On the coverage event: a wrong acceptance is impossible, and stopping undecided implies |p - θ| < ζ, so
    P(wrong acceptance) <= α' and the power is >= 1-α' outside [θ-ζ, θ+ζ], asymptotically (CLT; the guarantee needs
    many nonzero samples, which is why decisions wait for `min_nonzero` of them). The mixture parameter is tuned for
    sample size n_star (default: the fixed-width Bernoulli sample size at θ); any fixed value is valid.
    Small-sample correction: when p̂ < θ the H- check uses sd_n * sqrt(θ/p̂) (the variance a mean of θ would have
    for Bernoulli samples, conservative for splitting estimators whose sd scales like the mean). Low p̂ comes with
    low sd_n for skewed samples, which otherwise makes the upper bound too tight; as p̂ -> θ at a decision the factor
    -> 1, so the asymptotic guarantee is unchanged.
    With no nonzero sample at all, H- is accepted by an exact rule instead: for X in [0,1], P(X > 0) >= E[X], so
    P(n zeros | p >= θ) <= (1-θ)^n <= α'. Both modes credit the variance of non-Bernoulli (e.g. splitting) samples.
    """
    def __init__(self, theta: float, err_tols: ErrTols, indifference: float, max_samples: Optional[int],
                 mode: str = "anytime", min_nonzero: int = 10, n_star: Optional[int] = None, verbose: bool = False):
        super().__init__(theta, err_tols, indifference, max_samples)
        if theta - indifference <= 0 or theta + indifference >= 1:
            raise HypTestError(self.__str__() + ": [θ-ζ, θ+ζ] must lie in (0,1).")
        if mode not in ("anytime", "fixed_width"):
            raise HypTestError(self.__str__() + ": mode must be 'anytime' or 'fixed_width'.")
        self.mode = mode
        self.min_nonzero = min_nonzero
        self.verbose = verbose
        self.probit_alpha = norm.ppf(self.get_alpha())
        self.eps = indifference / (1+(norm.ppf(self.get_beta())/self.probit_alpha))
        self.cs_alpha = min(self.get_alpha(), self.get_beta())
        if n_star is None:
            n_star = math.ceil(self.probit_alpha ** 2 * theta * (1 - theta) / self.eps ** 2)
        log_inv = -2 * math.log(self.cs_alpha)
        self.rho2 = (log_inv + math.log(log_inv + 1)) / n_star
        self.n_all_zero = math.ceil(math.log(self.cs_alpha) / math.log1p(-theta))

    def __str__(self):
        return "Chow-Robbins [θ={:e}, (α,β)={}, ζ={:e}]".format(self.theta, self.err_tols, self.indifference)

    def run_test(self, sampler: Sampler) -> HypTestResult:
        if self.mode == "fixed_width":
            return self._run_fixed_width(sampler)
        return self._run_anytime(sampler)

    def _run_anytime(self, sampler: Sampler) -> HypTestResult:
        result = HypResult.INCONCLUSIVE
        self.tick()
        p_hat, ss_x, n, nonzero = 0.0, 0.0, 0, 0
        while self.max_samples is None or n < self.max_samples:
            x = sampler.sample()
            n += 1
            nonzero += x != 0
            p_hat, ss_x = update_sample_ests(x, p_hat, ss_x, n)
            if nonzero == 0:
                if n >= self.n_all_zero:
                    result = HypResult.ACCEPT_H_MINUS
                    break
                continue
            if nonzero < self.min_nonzero or n < 2:
                continue
            half = mixture_cs_half_width(math.sqrt(ss_x / (n - 1)), n, self.rho2, self.cs_alpha)
            half_minus = half * math.sqrt(max(1.0, self.theta / p_hat))
            if self.verbose and n % 10000 == 0:
                print(f"n: {n}, p_hat: {p_hat:.6g}, CS half-width: {half:.6g}")
            if p_hat - half > self.theta:
                result = HypResult.ACCEPT_H_PLUS
                break
            if p_hat + half_minus < self.theta:
                result = HypResult.ACCEPT_H_MINUS
                break
            if max(half, half_minus) < self.indifference / 2:
                break
        wall_time = self.tock()
        return HypTestResult(result, n, p_hat, ss_x / n, wall_time)

    def _run_fixed_width(self, sampler: Sampler) -> HypTestResult:
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
            if self.verbose and n % 500 == 0:
                print(f"n: {n}, p_hat: {p_hat:.6f}, half CI: {half_ci:.6f}, eps: {self.eps}")
            if 0 < half_ci < self.eps:
                break
        if (p_hat - half_ci) > self.theta:
            result = HypResult.ACCEPT_H_PLUS
        elif (p_hat + half_ci) < self.theta:
            result = HypResult.ACCEPT_H_MINUS
        wall_time = self.tock()
        return HypTestResult(result, n, p_hat, (ss_x / n), wall_time)
