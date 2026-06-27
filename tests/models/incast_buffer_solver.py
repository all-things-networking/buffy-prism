"""
Exact solver for the shared-buffer "incast" case study.

Dynamics (must EXACTLY mirror the PRISM .pm we will emit):
  - N senders. Each independently picks a start slot uniformly in {0,...,W}.
  - A sender that starts at slot t sends S packets back-to-back, one per slot,
    occupying slots t, t+1, ..., t+S-1.
  - Single shared buffer of size B, drains C packets per slot (service first,
    then admit arrivals; arrivals that don't fit are DROPPED).
  - Horizon = W + S slots (0 .. W+S-1); after that no sender is active.

Per slot tau:
    arrivals   = # senders active at tau           (offered load this slot)
    departures = min(q, C)
    room       = B - q + departures                (space after service)
    admitted   = min(arrivals, room)
    dropped    = arrivals - admitted
    q'         = q - departures + admitted
    drops     += dropped
    peak       = max(peak, arrivals)

Bad event  Q : total drops >= p
Condition  A : a predicate over INPUT-describing features (peak concurrency,
               # early starters, spread of starts, ...). These features are a
               function of the start-time pattern ALONE (independent of buffer).

Because senders are exchangeable, the buffer behaviour and all input features
depend only on the histogram h = (h_0,...,h_W) of start slots (h_j = # senders
starting at slot j). We enumerate every histogram with sum = N and weight it by
its multinomial probability  N!/(prod h_j!) / (W+1)^N  -> EXACT distribution.
"""

from math import comb, factorial
from itertools import product
from functools import lru_cache


def histograms(N, nbins):
    """Yield every (h_0,...,h_{nbins-1}) with non-negative ints summing to N."""
    if nbins == 1:
        yield (N,)
        return
    for first in range(N + 1):
        for rest in histograms(N - first, nbins - 1):
            yield (first,) + rest


def multinomial_weight(h, N, W):
    coef = factorial(N)
    for hj in h:
        coef //= factorial(hj)
    return coef / (W + 1) ** N


def simulate(h, N, S, W, B, C):
    """Run the deterministic buffer dynamics for one start-histogram h.
    Returns a dict of outcome + input features."""
    HORIZON = W + S
    q = 0
    drops = 0
    peak = 0
    for tau in range(HORIZON):
        # arrivals = senders active at tau = sum of h_j for j in (tau-S, tau]
        lo = max(0, tau - S + 1)
        hi = min(W, tau)
        arrivals = sum(h[j] for j in range(lo, hi + 1))
        departures = min(q, C)
        room = B - q + departures
        admitted = min(arrivals, room)
        dropped = arrivals - admitted
        q = q - departures + admitted
        drops += dropped
        if arrivals > peak:
            peak = arrivals
    # ---- input-describing features (function of h alone) ----
    starts = [j for j in range(W + 1) for _ in range(h[j])]  # multiset of starts
    spread = (max(starts) - min(starts)) if starts else 0
    return {
        "drops": drops,
        "peak": peak,             # peak concurrency = peak offered load
        "spread": spread,         # max_start - min_start
        "h": h,
    }


def analyze(N, S, W, B, C, p, conditions):
    """conditions: dict name -> function(outcome_dict) -> bool.
    Returns baseline P[Q] and, per condition, P[A], P[Q|A], lift."""
    PQ = 0.0
    condP = {name: 0.0 for name in conditions}     # P[A]
    condPQ = {name: 0.0 for name in conditions}    # P[Q & A]
    for h in histograms(N, W + 1):
        w = multinomial_weight(h, N, W)
        out = simulate(h, N, S, W, B, C)
        Q = out["drops"] >= p
        if Q:
            PQ += w
        for name, pred in conditions.items():
            if pred(out):
                condP[name] += w
                if Q:
                    condPQ[name] += w
    results = {"P[Q]": PQ, "conditions": {}}
    for name in conditions:
        pa = condP[name]
        pqa = condPQ[name]
        cond = (pqa / pa) if pa > 0 else float("nan")
        results["conditions"][name] = {
            "P[A]": pa,
            "P[Q&A]": pqa,
            "P[Q|A]": cond,
            "lift": (cond / PQ) if PQ > 0 else float("nan"),
        }
    return results


def pretty(name, params, res):
    N, S, W, B, C, p = params
    print(f"\n=== {name}: N={N} S={S} W={W} B={B} C={C} p={p}  (HORIZON={W+S}) ===")
    print(f"  baseline  P[Q] = P[drops>={p}] = {res['P[Q]']:.4f}")
    print(f"  {'condition A':<26} {'P[A]':>8} {'P[Q|A]':>8} {'lift':>7}")
    for cname, c in res["conditions"].items():
        print(f"  {cname:<26} {c['P[A]']:>8.4f} {c['P[Q|A]']:>8.4f} {c['lift']:>7.2f}x")


if __name__ == "__main__":
    # Committed parameters (match incast_buffer_dtmc.pm): N,S,W,B,C,p
    params = (5, 3, 8, 4, 2, 1)
    N, S, W, B, C, p = params
    conditions = {
        "peak>=4 (mild,informative)": lambda o: o["peak"] >= 4,
        "peak>=5 (all synchronized)": lambda o: o["peak"] >= 5,
        "peak>=3 (mild,weak)":        lambda o: o["peak"] >= 3,
        "peak<=2 (safety cert.)":     lambda o: o["peak"] <= 2,
        "spread<=3 (starts bunched)": lambda o: o["spread"] <= 3,
    }
    res = analyze(N, S, W, B, C, p, conditions)
    pretty("incast", params, res)
