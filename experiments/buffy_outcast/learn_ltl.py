"""
Learn bounded-LTL conditions on the switch's input that separate the runs where the bad event Q happens.

Traces come from oc_traces.py (the compiled Buffy model, stepped natively). Atoms are read at each
time-step boundary t (the step that ended at t): aA / aB - port A / port B delivered a packet.
Formulas (enumerated, then scored on a training half and re-scored on a held-out half):
  run(p, k, [a, b))   F (time in [a, b) && p && X p && ... ) : k consecutive p-steps starting in [a, b)
  ~run(p, k, [a, b))  its negation (k = 1: G over [a, b) of !p)
  conjunctions of two of those.
A condition is reported with P[cond] (how mild it is), P[Q | cond] and the lift P[Q | cond] / P[Q].

Usage: python learn_ltl.py traces.npz Q [min_p] [top] [upto] [out.json]
  Q: starveB:<thr>  (B's window deliveries got_B <= thr at T)   or   toB:<k> (B's timeouts in the window >= k)
"""
import itertools
import json
import sys

import numpy as np


def atoms(tr, names):
    g = lambda k: tr[:, :, names.index(k)].astype(bool)
    aA, aB = g("aA"), g("aB")
    return {
        "aA": aA, "aB": aB, "!aA": ~aA, "!aB": ~aB,
        "aA&aB": aA & aB, "aB&!aA": aB & ~aA, "aA&!aB": aA & ~aB, "!aA&!aB": ~aA & ~aB,
    }


PRED = {"aA": "outcast.aA == 1", "aB": "outcast.aB == 1", "!aA": "outcast.aA == 0", "!aB": "outcast.aB == 0",
        "aA&aB": "(outcast.aA == 1 && outcast.aB == 1)", "aB&!aA": "(outcast.aB == 1 && outcast.aA == 0)",
        "aA&!aB": "(outcast.aA == 1 && outcast.aB == 0)", "!aA&!aB": "(outcast.aA == 0 && outcast.aB == 0)"}


def to_buffy(f):
    """ A learned formula in Buffy's bounded LTL (time-step boundaries; `time` is the step counter). """
    def one(g):
        neg = g.startswith("~")
        body = g.lstrip("~")[4:-1]
        atom, k, iv = body.split(",", 2)
        a, b = (int(x) for x in iv.strip("[)").split(","))
        p = PRED[atom]
        chain = p
        for _ in range(int(k) - 1):
            chain = f"{p} && X ({chain})" if chain != p else f"{p} && X {p}"
        x = f"F<={b} (time >= {a} && time < {b} && {chain})"
        return f"!({x})" if neg else f"({x})"
    return " && ".join(one(g.strip()) for g in f.split(" & "))


def run_starts(p, k):
    """ s[r, t]: p holds at t, t+1, ..., t+k-1 (false where that runs past the trace). """
    n, T1 = p.shape
    s = np.ones((n, T1), dtype=bool)
    for j in range(k):
        sh = np.zeros_like(p)
        sh[:, :T1 - j] = p[:, j:]
        s &= sh
    return s


def main():
    d = np.load(sys.argv[1])
    tr, names = d["traces"], list(d["names"])
    qspec = sys.argv[2]
    min_p = float(sys.argv[3]) if len(sys.argv) > 3 else 0.1
    top = int(sys.argv[4]) if len(sys.argv) > 4 else 15
    upto = int(sys.argv[5]) if len(sys.argv) > 5 else None   # only intervals ending by `upto` (predictive)
    T = tr.shape[1] - 1
    nf_b = next(n for n in names if n.startswith("got_") and n != "got_0")
    kind, val = qspec.split(":")
    if kind == "starveB":
        Q = tr[:, T, names.index(nf_b)] <= int(val)
    else:
        toB = tr[:, :, names.index(nf_b.replace("got_", "to_"))]
        Q = (toB[:, T] - toB[:, T // 2]) >= int(val)
    A = atoms(tr, names)
    n = len(Q)
    train, test = np.arange(n) < n // 2, np.arange(n) >= n // 2
    pq = Q.mean()
    print(f"runs={n} T={T} Q={qspec}: P[Q]={pq:.4f}")
    edges = [0, 40, 80, 120, 160]
    intervals = [(a, b) for a in edges for b in edges if a < b and b <= (upto or T)]
    base = {}
    for (pn, p), k, (a, b) in itertools.product(A.items(), [1, 2, 3, 4, 6, 8], intervals):
        st = run_starts(p, k)[:, a:b].any(axis=1)
        base[f"run({pn},{k},[{a},{b}))"] = st
        base[f"~run({pn},{k},[{a},{b}))"] = ~st
    # keep the singles that are neither (almost) always nor (almost) never true
    singles = {f: v for f, v in base.items() if 0.02 <= v[train].mean() <= 0.98}
    print(f"{len(singles)} single formulas")

    def score(v, idx):
        pc = v[idx].mean()
        return pc, (Q[idx] & v[idx]).mean() / pc if pc > 0 else float("nan")

    rows = []
    for f, v in singles.items():
        pc, pqc = score(v, train)
        if pc >= min_p:
            rows.append((pqc, pc, f, v))
    rows.sort(key=lambda r: -r[0])
    # conjunctions of the best 60 dangerous and 60 protective singles
    cand = rows[:60] + rows[-60:]
    conj = []
    for (q1, p1, f1, v1), (q2, p2, f2, v2) in itertools.combinations(cand, 2):
        v = v1 & v2
        pc, pqc = score(v, train)
        if pc >= min_p:
            conj.append((pqc, pc, f"{f1} & {f2}", v))
    allrows = rows + conj
    out = []
    for title, sel in (("dangerous (highest P[Q|cond])", sorted(allrows, key=lambda r: -r[0])[:top]),
                       ("protective (lowest P[Q|cond])", sorted(allrows, key=lambda r: r[0])[:top])):
        print(f"\n{title}, P[cond] >= {min_p}; train | held-out")
        for pqc, pc, f, v in sel:
            pc2, pqc2 = score(v, test)
            print(f"  P[c]={pc:.3f} P[Q|c]={pqc:.3f} lift={pqc / pq:.2f} | P[c]={pc2:.3f} P[Q|c]={pqc2:.3f}   {f}")
            out.append({"kind": title.split()[0], "formula": f, "buffy": to_buffy(f), "train": [pc, pqc],
                        "heldout": [pc2, pqc2]})
    if len(sys.argv) > 6:
        json.dump({"Q": qspec, "PQ": pq, "conditions": out}, open(sys.argv[6], "w"), indent=1)


if __name__ == "__main__":
    main()
