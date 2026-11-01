"""
Chernoff-Hoeffding (relative-entropy) tail bounds for means of i.i.d. [0,1]-valued samples, and the
threshold searches used by the adaptive (multistage inverse sampling) procedures.

Notation follows Chen (2009), "A New Framework of Multistage Estimation", Sec. 7:
X_1, X_2, ... i.i.d. in [0,1] with mean mu, S_n = X_1 + ... + X_n, and the Bernoulli relative entropy

    KL(z || q) = z ln(z/q) + (1-z) ln((1-z)/(1-q)) = -M_B(z, q).

Hoeffding (1963, Thm. 1) gives, for ANY distribution on [0,1] (not only Bernoulli):

    P(S_n >= n z) <= exp(-n KL(z || mu))   for mu <= z <= 1,               (H+)
    P(S_n <= n z) <= exp(-n KL(z || mu))   for 0 <= z <= mu.               (H-)

Facts used by the procedures (all elementary; see the module docstrings that use them):
  (F1) q -> KL(z || q) is decreasing on (0, z] and increasing on [z, 1), since
       d/dq KL(z || q) = (q - z) / (q (1 - q)).
  (F2) For fixed gamma, theta, n -> n KL(gamma/n || theta) is strictly decreasing while gamma/n > theta
       and strictly increasing while gamma/n < theta, since its derivative in n is
       ln((1 - gamma/n) / (1 - theta)).
  (F3) Because X_i >= 0, S_n is non-decreasing in n, so for the first-passage time
       n(gamma) = min{n : S_n >= gamma} we have {n(gamma) <= m} = {S_m >= gamma}.
"""
import math
from typing import Optional

# Relative slack on every "bound <= level" comparison, so that floating-point rounding can only make
# the procedures more conservative, never less.
_SLACK = 1e-12


def kl_bernoulli(z: float, q: float) -> float:
    """ KL(z || q) for z in [0,1], q in [0,1]; +inf when q in {0,1} and z != q. """
    if not (0.0 <= z <= 1.0 and 0.0 <= q <= 1.0):
        raise ValueError(f"kl_bernoulli: arguments must lie in [0,1], got z={z}, q={q}")
    if z == q:
        return 0.0
    if q == 0.0 or q == 1.0:
        return math.inf
    kl = 0.0
    if z > 0.0:
        kl += z * math.log(z / q)
    if z < 1.0:
        kl += (1.0 - z) * (math.log1p(-z) - math.log1p(-q))
    return max(kl, 0.0)


def massart_exponent(z: float, q: float) -> float:
    """
    Massart's exponent M(z, q) = 9 (z-q)^2 / (2 (z+2q)(z+2q-3)) <= 0 for z in [0,1], q in (0,1).
    It satisfies -KL(z || q) <= M(z, q) (Chen 2009, Lemma 1, eqs. (39),(41)), i.e. it gives a
    closed-form but strictly LOOSER bound than the relative entropy.
    """
    if not (0.0 <= z <= 1.0) or not (0.0 < q < 1.0):
        raise ValueError(f"massart_exponent: need z in [0,1], q in (0,1), got z={z}, q={q}")
    return 9.0 * (z - q) ** 2 / (2.0 * (z + 2.0 * q) * (z + 2.0 * q - 3.0))


def meets(exponent: float, log_inv_level: float) -> bool:
    """ True iff exp(-exponent) <= exp(-log_inv_level), with a conservative slack. """
    return exponent >= log_inv_level * (1.0 + _SLACK) + _SLACK


def upper_tail_bound(m: int, gamma: float, mu: float) -> float:
    """ Bound on P(S_m >= gamma | mean mu) from (H+); 1.0 if gamma/m <= mu (no information). """
    if m <= 0:
        return 1.0 if gamma <= 0 else 0.0
    z = gamma / m
    if z > 1.0:
        return 0.0
    if z <= mu:
        return 1.0
    return math.exp(-m * kl_bernoulli(z, mu))


def lower_tail_bound(m: int, gamma: float, mu: float) -> float:
    """ Bound on P(S_m < gamma | mean mu) from (H-); 1.0 if gamma/m >= mu (no information). """
    if m <= 0:
        return 1.0 if gamma > 0 else 0.0
    z = gamma / m
    if z >= mu:
        return 1.0
    return math.exp(-m * kl_bernoulli(z, mu))


def last_upper_checkpoint(gamma: float, theta: float, log_inv_level: float) -> Optional[int]:
    """
    N+ = max{ n >= ceil(gamma) : gamma/n > theta and n KL(gamma/n || theta) >= log_inv_level }, or None.

    Guarantee: for every mu <= theta, P(S_{N+} >= gamma | mu) <= exp(-log_inv_level), by (H+) and (F1).
    By (F2) the feasible set is an initial segment of integers, so a bisection finds its maximum.
    """
    lo = max(1, math.ceil(gamma))
    hi = math.ceil(gamma / theta) - 1          # largest n with gamma/n > theta
    phi = lambda n: n * kl_bernoulli(gamma / n, theta)
    if hi < lo or not meets(phi(lo), log_inv_level):
        return None
    while lo < hi:                              # invariant: phi(lo) meets the level
        mid = (lo + hi + 1) // 2
        if meets(phi(mid), log_inv_level):
            lo = mid
        else:
            hi = mid - 1
    assert gamma / lo > theta and meets(phi(lo), log_inv_level)
    return lo


def first_lower_checkpoint(gamma: float, theta: float, log_inv_level: float) -> int:
    """
    M- = min{ m : gamma/m < theta and m KL(gamma/m || theta) >= log_inv_level }.

    Guarantee: for every mu >= theta, P(S_{M-} < gamma | mu) <= exp(-log_inv_level), by (H-) and (F1).
    By (F2) the feasible set is a terminal segment of integers (non-empty: the exponent grows like
    m ln(1/(1-theta))), so a bisection finds its minimum.
    """
    lo = math.floor(gamma / theta) + 1          # smallest m with gamma/m < theta
    psi = lambda m: m * kl_bernoulli(gamma / m, theta)
    hi = lo
    while not meets(psi(hi), log_inv_level):
        hi *= 2
    while lo < hi:                              # invariant: psi(hi) meets the level
        mid = (lo + hi) // 2
        if meets(psi(mid), log_inv_level):
            hi = mid
        else:
            lo = mid + 1
    assert gamma / hi < theta and meets(psi(hi), log_inv_level)
    return hi
