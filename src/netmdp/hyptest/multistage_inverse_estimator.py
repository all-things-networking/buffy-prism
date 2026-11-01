"""
Multistage inverse-sampling estimator of mu = E[X], X in [0,1], with a guaranteed RELATIVE error:
    P(|mu_hat - mu| < eps mu) >= 1 - delta   for every distribution on [0,1] with mean mu in (0,1).
This is Theorem 41 of Chen (2009), "A New Framework of Multistage Estimation", Sec. 7.2 (Chernoff-Hoeffding
exponent M_B = -KL), or Theorem 42 / the RELM rule of Chen & Xu (2013) with Massart's exponent M.

Scheme. Thresholds 1/eps < gamma_1 < ... < gamma_s, L = ln(2s/delta). Stage l waits for the first passage
n_l = min{n : S_n >= gamma_l} (stages share one sample path) and sets mu_hat_l = gamma_l / n_l.
Sampling stops at the first stage l with D_l(n_l) = 1, where D_s == 1 and, for l < s, D_l(n) = C1 and C2 with
  C1: n KL(gamma/n || gamma/(n(1+eps))) >= L,
  C2: gamma/(n(1-eps)) >= 1, or (n-1) KL(gamma/(n-1) || gamma/(n(1-eps))) >= L.
(With bound="massart", -M replaces KL in C1/C2; since KL >= -M this only makes D_l harder to satisfy.)

Proof of the guarantee (one side each; the two together give delta). Write P_l^+ = P(mu_hat_l >= (1+eps)mu, D_l = 1)
and P_l^- = P(mu_hat_l <= (1-eps)mu, D_l = 1). Since {stop at l} is contained in {D_l = 1},
P(mu_hat >= (1+eps)mu) <= sum_l P_l^+ and P(mu_hat <= (1-eps)mu) <= sum_l P_l^-; it suffices that
P_l^{+/-} <= delta/(2s).
  Upper. Let A = {n : D_l(n) = 1, gamma/n >= (1+eps)mu} (finite) and n* = max A. Then the event is contained in
  {n_l <= n*} = {S_{n*} >= gamma} (F3). As mu <= gamma/(n*(1+eps)) < gamma/n*, (H+) and (F1) give
  P <= exp(-n* KL(gamma/n* || gamma/(n*(1+eps)))) <= exp(-L) by C1 at n*.
  Lower. Let B = {n : D_l(n) = 1, gamma/n <= (1-eps)mu} and n_* = min B. Then n_* >= gamma/((1-eps)mu) > gamma
  > 1/eps, so x := gamma/(n_*-1) < gamma/(n_*(1-eps)) =: t <= mu < 1. The event is contained in
  {n_l >= n_*} = {S_{n_*-1} < gamma}, and (H-) with (F1) gives P <= exp(-(n_*-1) KL(x || t)) <= exp(-L) by C2.
  Final stage. D_s == 1 is legitimate because the constructor checks that C1 and C2 hold for EVERY feasible
  n >= ceil(gamma_s): with KL(z || cz) = z * int_c^1 (1-u)/(u(1-zu)) du (substitute t = zu in
  KL(z||q) = int_q^z (z-t)/(t(1-t)) dt) one gets
     n KL(gamma/n || gamma/(n(1+eps))) >= gamma (ln(1+eps) - eps/(1+eps))             for all n,
     (n-1) KL(gamma/(n-1) || c_n gamma/(n-1)) >= gamma (c_n - 1 - ln c_n),  c_n = (n-1)/(n(1-eps)),
  and c -> c - 1 - ln c is increasing on c > 1 while c_n is increasing in n, so the second bound is smallest
  at n = ceil(gamma_s) (which must exceed 1/eps). []
Note: like any distribution-free bound for [0,1] variables, the required number of samples is about
gamma_s / mu ~ 2 ln(2s/delta) / (eps^2 mu) whatever the variance of X: the bound is attained by Bernoulli
samples, so it cannot credit the variance reduction of an importance-splitting estimator.
"""
import math
from dataclasses import dataclass
from typing import Optional

from src.netmdp.hyptest.chernoff_bounds import kl_bernoulli, massart_exponent, meets
from src.netmdp.hyptest.hyptest import HypTestError
from src.netmdp.sampler.sampler import Sampler


@dataclass(frozen=True)
class EstimateResult:
    estimate: float
    n: int
    stage: int
    n_stages: int


class MultistageInverseEstimator:
    def __init__(self, eps: float, delta: float, growth: float = 1.5, n_stages: Optional[int] = None,
                 bound: str = "kl"):
        if not (0 < eps < 1 and 0 < delta < 1):
            raise HypTestError("MultistageInverseEstimator: need 0 < eps < 1 and 0 < delta < 1.")
        if growth <= 1:
            raise HypTestError("MultistageInverseEstimator: growth must exceed 1.")
        if bound not in ("kl", "massart"):
            raise HypTestError("MultistageInverseEstimator: bound must be 'kl' or 'massart'.")
        self.eps, self.delta, self.growth, self.bound = eps, delta, growth, bound
        if n_stages is None:
            n_stages = 1
            for _ in range(20):  # fixed point: geometric stages from just above 1/eps up to gamma_s
                s_new = 1 + math.ceil(math.log(self._final_gamma(n_stages) * eps) / math.log(growth))
                if s_new == n_stages:
                    break
                n_stages = s_new
        self.n_stages = n_stages
        self.log_inv = math.log(2 * n_stages / delta)
        gamma_s = self._final_gamma(n_stages)
        gamma_1 = max(gamma_s * growth ** -(n_stages - 1), (1.0 + 1e-9) / eps)
        self.gammas = [min(gamma_1 * growth ** l, gamma_s) for l in range(n_stages - 1)] + [gamma_s]
        assert all(g > 1 / eps for g in self.gammas) and self._final_stage_ok(gamma_s, self.log_inv)

    def __str__(self):
        return "Multistage inverse estimator [ε={:e}, δ={:e}, s={}]".format(self.eps, self.delta, self.n_stages)

    def _final_stage_ok(self, gamma: float, log_inv: float) -> bool:
        eps = self.eps
        n0 = math.ceil(gamma)
        if n0 <= 1 / eps:
            return False
        c = (n0 - 1) / (n0 * (1 - eps))
        return (meets(gamma * (math.log1p(eps) - eps / (1 + eps)), log_inv)
                and meets(gamma * (c - 1 - math.log(c)), log_inv))

    def _final_gamma(self, n_stages: int) -> float:
        log_inv = math.log(2 * n_stages / self.delta)
        hi = max(1.0, log_inv * (1 + self.eps) / ((1 + self.eps) * math.log1p(self.eps) - self.eps))
        while not self._final_stage_ok(hi, log_inv):
            hi *= 1.01
        return hi

    def _exponent(self, z: float, q: float) -> float:
        return kl_bernoulli(z, q) if self.bound == "kl" else -massart_exponent(z, q)

    def stop_condition(self, gamma: float, n: int) -> bool:
        """ D_l(n) for an intermediate stage with threshold gamma (see module docstring). """
        eps = self.eps
        c1 = meets(n * self._exponent(gamma / n, gamma / (n * (1 + eps))), self.log_inv)
        t = gamma / (n * (1 - eps))
        c2 = t >= 1 or meets((n - 1) * self._exponent(gamma / (n - 1), t), self.log_inv)
        return c1 and c2

    def estimate(self, sampler: Sampler) -> EstimateResult:
        s_n, n = 0.0, 0
        for l, gamma in enumerate(self.gammas):
            while s_n < gamma:
                x = sampler.sample()
                if not 0.0 <= x <= 1.0:
                    raise HypTestError(f"{self}: sample {x} outside [0,1].")
                s_n += x
                n += 1
            if l == self.n_stages - 1 or self.stop_condition(gamma, n):
                return EstimateResult(gamma / n, n, l + 1, self.n_stages)
        raise AssertionError("unreachable: the final stage always stops")
