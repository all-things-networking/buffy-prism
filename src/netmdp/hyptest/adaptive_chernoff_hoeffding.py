"""
Adaptive Chernoff-Hoeffding test: a multistage inverse-sampling test of P_{>theta}(phi) in the framework of
Reijsbergen et al. (2015), built on the multistage inverse-sampling scheme of Chen (2009, Sec. 7.2) and the
Chernoff-Hoeffding (relative-entropy) bound for [0,1]-valued samples.

Setting. Samples X_1, X_2, ... are i.i.d., X_i in [0,1], mean mu. They need NOT be Bernoulli, so the
test applies both to crude Monte Carlo indicators 1_phi(omega) and to unbiased importance-splitting
estimators in [0,1] (e.g. fixed-effort products prod_l s_l/n_l). S_n = X_1 + ... + X_n.

Hypotheses (Reijsbergen et al., eq. (2)): H+ : mu > theta,  H- : mu < theta; power-indifference level zeta.

Design. Thresholds gamma_1 < ... < gamma_s (geometric, ratio `growth`) and L = ln(s/alpha). For each stage l,
  N+_l = max{n : gamma_l/n > theta,  n KL(gamma_l/n || theta) >= L}            (may not exist)
  M-_l = min{m : gamma_l/m < theta,  m KL(gamma_l/m || theta) >= L}
(see chernoff_bounds.last_upper_checkpoint / first_lower_checkpoint).

Procedure. Draw samples one at a time. After the n-th sample:
  * accept H+ if S_n >= gamma_l and n <= N+_l for some l          (i.e. the first passage n(gamma_l) <= N+_l);
  * accept H- if n = M-_l and S_n < gamma_l for some l;
  * declare INCONCLUSIVE once no check can fire any more (at the latest at n = max_l M-_l).
(The two acceptances can never fire together: H+ needs n < gamma_l/theta and H- needs n > gamma_k/theta with
gamma_k > S_n >= gamma_l.)

Theorem (errors of the first kind, Reijsbergen eqs. (3),(4)). For every distribution on [0,1] with mean mu,
  P(accept H+ | mu <= theta) <= alpha   and   P(accept H- | mu >= theta) <= alpha.
Proof. Analyse the infinite sample path; stopping early only removes acceptances. By (F3) of chernoff_bounds,
  {accept H+} subset U_l {n(gamma_l) <= N+_l} = U_l {S_{N+_l} >= gamma_l}.
For mu <= theta < gamma_l/N+_l, (H+) and (F1) give P(S_{N+_l} >= gamma_l) <= exp(-N+_l KL(gamma_l/N+_l || theta))
<= exp(-L) = alpha/s. Union bound over the s stages: <= alpha. Symmetrically
  {accept H-} subset U_l {S_{M-_l} < gamma_l}, and for mu >= theta > gamma_l/M-_l, (H-) and (F1) give
P(S_{M-_l} < gamma_l) <= exp(-M-_l KL(gamma_l/M-_l || theta)) <= alpha/s. []

Theorem (power, Reijsbergen eqs. (5),(6)). The constructor picks gamma_s so that the computed quantities
  e+ = sum_l exp(-M-_l KL(gamma_l/M-_l || theta+zeta)) + exp(-N+_s KL(gamma_s/N+_s || theta+zeta)),
  e- = sum_l exp(-N+_l KL(gamma_l/N+_l || theta-zeta)) + exp(-M-_s KL(gamma_s/M-_s || theta-zeta))
are both <= beta (each exponential term read as 1 when its bound is not informative, see
upper_tail_bound/lower_tail_bound). Then
  P(not accept H+ | mu >= theta+zeta) <= e+ <= beta   and   P(not accept H- | mu <= theta-zeta) <= e- <= beta,
provided max_samples (if set) is at least `worst_case_samples`.
Proof. If mu >= theta+zeta and H+ is not accepted, then either some H- check fired, or the stage-s H+ check
did not: {not A+} subset U_l {S_{M-_l} < gamma_l} U {S_{N+_s} < gamma_s}. Each event is bounded by (H-) at the
true mu, and by (F1) the bound only decreases as mu moves above theta+zeta >= gamma/m. The H- case is
symmetric with (H+). []

The test is class II in Reijsbergen's taxonomy (it may end INCONCLUSIVE inside the indifference region), and
is adaptive: when |mu - theta| is large, an early stage (small gamma_l) decides after roughly
gamma_l / mu samples, instead of the worst-case sample size of a fixed-N Chernoff-CI test.
Because it uses the relative-entropy form of the Chernoff-Hoeffding bound rather than the additive form
exp(-2 n t^2), its worst-case sample size scales like theta ln(s/alpha) / zeta^2 instead of
ln(1/alpha) / (2 zeta^2), which matters for rare-event thresholds theta << 1.
"""
import math
from dataclasses import dataclass
from typing import Optional

from src.netmdp.hyptest.chernoff_bounds import (kl_bernoulli, last_upper_checkpoint, first_lower_checkpoint,
                                               upper_tail_bound, lower_tail_bound)
from src.netmdp.hyptest.chow_robbins import update_sample_ests
from src.netmdp.hyptest.hyptest import HypTest, ErrTols, HypTestResult, HypResult, HypTestError
from src.netmdp.sampler.sampler import Sampler


@dataclass(frozen=True)
class AchStage:
    gamma: float            # inverse-sampling threshold on S_n
    n_plus: Optional[int]   # accept H+ if S reaches gamma by this many samples (None: no H+ check)
    m_minus: int            # accept H- if S_{m_minus} < gamma


@dataclass(frozen=True)
class AchDesign:
    stages: tuple[AchStage, ...]
    power_err_plus: float   # certified bound on P(not accept H+ | mu >= theta + zeta)
    power_err_minus: float  # certified bound on P(not accept H- | mu <= theta - zeta)

    def worst_case_samples(self) -> int:
        return max(st.m_minus for st in self.stages)


def _build_design(theta: float, alpha: float, zeta: float, n_stages: int, gamma_s: float,
                  growth: float) -> AchDesign:
    log_inv = math.log(n_stages / alpha)
    stages = []
    for l in range(n_stages):
        gamma = gamma_s * growth ** -(n_stages - 1 - l)
        stages.append(AchStage(gamma,
                               last_upper_checkpoint(gamma, theta, log_inv),
                               first_lower_checkpoint(gamma, theta, log_inv)))
    last = stages[-1]
    # P(some H- check fires | mu = theta+zeta) + P(S_{N+_s} < gamma_s | mu = theta+zeta)
    err_plus = sum(lower_tail_bound(st.m_minus, st.gamma, theta + zeta) for st in stages)
    err_plus += 1.0 if last.n_plus is None else lower_tail_bound(last.n_plus, last.gamma, theta + zeta)
    # P(some H+ check fires | mu = theta-zeta) + P(S_{M-_s} >= gamma_s | mu = theta-zeta)
    err_minus = sum(upper_tail_bound(st.n_plus, st.gamma, theta - zeta) for st in stages if st.n_plus is not None)
    err_minus += upper_tail_bound(last.m_minus, last.gamma, theta - zeta)
    return AchDesign(tuple(stages), min(err_plus, 1.0), min(err_minus, 1.0))


def design_test(theta: float, alpha: float, beta: float, zeta: float, n_stages: int,
                growth: float) -> AchDesign:
    """ Smallest (up to bisection tolerance) final threshold gamma_s whose design certifies power 1-beta. """
    ok = lambda d: d.power_err_plus <= beta and d.power_err_minus <= beta
    hi = math.log(n_stages / alpha)
    while not ok(_build_design(theta, alpha, zeta, n_stages, hi, growth)):
        lo, hi = hi, 2.0 * hi
        if hi > 1e15:
            raise HypTestError("design_test: no feasible final threshold found")
    lo = hi / 2.0
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        if ok(_build_design(theta, alpha, zeta, n_stages, mid, growth)):
            hi = mid
        else:
            lo = mid
    design = _build_design(theta, alpha, zeta, n_stages, hi, growth)
    assert ok(design)  # the guarantee rests on this explicit check, not on monotonicity of the search
    return design


class AdaptiveChernoffHoeffding(HypTest):
    """ Adaptive (multistage inverse sampling) Chernoff-Hoeffding test; see the module docstring. """
    def __init__(self, theta: float, err_tols: ErrTols, indifference: float, max_samples: Optional[int],
                 growth: float = 2.0, n_stages: Optional[int] = None):
        super().__init__(theta, err_tols, indifference, max_samples)
        if theta - indifference <= 0 or theta + indifference >= 1:
            raise HypTestError(self.__str__() + ": [θ-ζ, θ+ζ] must lie in (0,1).")
        if not (0 < self.get_alpha() < 1 and 0 < self.get_beta() < 1):
            raise HypTestError(self.__str__() + ": α and β must lie in (0,1).")
        if growth <= 1:
            raise HypTestError(self.__str__() + ": growth must exceed 1.")
        self.growth = growth
        self.design = self._choose_design(n_stages)

    def __str__(self):
        return "Adaptive Chernoff-Hoeffding [θ={:e}, (α,β)={}, ζ={:e}]".format(self.theta, self.err_tols,
                                                                           self.indifference)

    def _choose_design(self, n_stages: Optional[int]) -> AchDesign:
        args = (self.theta, self.get_alpha(), self.get_beta(), self.indifference)
        if n_stages is not None:
            return design_test(*args, n_stages, self.growth)
        # Number of stages: enough geometric steps to reach down from gamma_s to the smallest gamma that admits
        # an H+ check (gamma ln(1/theta) >= ln(s/alpha)). Any s is valid; this only tunes efficiency.
        s = 1
        for _ in range(20):
            design = design_test(*args, s, self.growth)
            gamma_min = math.log(s / self.get_alpha()) / -math.log(self.theta)
            s_new = 1 + max(0, math.ceil(math.log(design.stages[-1].gamma / gamma_min) / math.log(self.growth)))
            if s_new == s:
                return design
            s = s_new
        return design

    def run_test(self, sampler: Sampler) -> HypTestResult:
        stages = self.design.stages
        n_max = self.design.worst_case_samples()
        if self.max_samples is not None:
            n_max = min(n_max, self.max_samples)
        result = HypResult.INCONCLUSIVE
        s_n, mean, ss, n = 0.0, 0.0, 0.0, 0
        self.tick()
        while n < n_max:
            x = sampler.sample()
            if not 0.0 <= x <= 1.0:
                raise HypTestError(f"{self}: sample {x} outside [0,1]; the Chernoff-Hoeffding bound does not apply.")
            n += 1
            s_n += x
            mean, ss = update_sample_ests(x, mean, ss, n)
            if any(s_n >= st.gamma and st.n_plus is not None and n <= st.n_plus for st in stages):
                result = HypResult.ACCEPT_H_PLUS
                break
            if any(n == st.m_minus and s_n < st.gamma for st in stages):
                result = HypResult.ACCEPT_H_MINUS
                break
            h_plus_alive = any(st.n_plus is not None and n < st.n_plus for st in stages)
            h_minus_alive = any(n < st.m_minus and s_n < st.gamma for st in stages)
            if not (h_plus_alive or h_minus_alive):
                break
        wall_time = self.tock()
        return HypTestResult(result, n, mean, ss / n if n else 0.0, wall_time)
