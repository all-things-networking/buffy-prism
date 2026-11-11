"""
Learn conditions on the buggy FQ model's input that make Q (the thin flow served >= 4 times while all four
bulk queues are backlogged) likely or unlikely. Histories come from fq_histories.py (a weighted sample:
every Q run, a fraction of the others).

Formula families, over time-step boundaries 1..T (boundary t follows step t-1):
  run(p, k, [a, b))    F (time in [a, b) && p && X p && ... ): k consecutive steps with p, starting in [a, b)
  ~run(...)            its negation
  by(b, <= c)          G (time != b || cenq <= c): at most c thin-flow packets by boundary b
  by(b, >= c)          likewise at least c
  and conjunctions of two.
Atoms: a5 (thin-flow arrivals in the step) == 0, == 1, <= 1, >= 1, >= 2, >= 3; ab (bulk arrivals, all four queues
together) <= 4, >= 8, >= 12. Conditions that read only the thin flow ("thin") can be certified exactly with
--condition-on; the others ("bulk") by rejection.

Scored on a training half; re-scored on a held-out half. Reported: P[c], P[Q | c] and the lift over P[Q].

Usage: python learn_fq.py histories.npz [min_p] [top] [out.json]
"""
import itertools
import json
import sys

import numpy as np

THIN = {"a5=0": lambda h5, hb: h5 == 0, "a5=1": lambda h5, hb: h5 == 1, "a5<=1": lambda h5, hb: h5 <= 1,
        "a5>=1": lambda h5, hb: h5 >= 1, "a5>=2": lambda h5, hb: h5 >= 2, "a5>=3": lambda h5, hb: h5 >= 3}
BULK = {"ab<=4": lambda h5, hb: hb <= 4, "ab>=8": lambda h5, hb: hb >= 8, "ab>=12": lambda h5, hb: hb >= 12}
PRED = {"a5=0": "fq.a5 == 0", "a5=1": "fq.a5 == 1", "a5<=1": "fq.a5 <= 1", "a5>=1": "fq.a5 >= 1", "a5>=2": "fq.a5 >= 2", "a5>=3": "fq.a5 >= 3",
        "ab<=4": "fq.ab <= 4", "ab>=8": "fq.ab >= 8", "ab>=12": "fq.ab >= 12"}


def run_starts(p, k):
    n, L = p.shape
    s = np.ones((n, L), dtype=bool)
    for j in range(k):
        sh = np.zeros_like(p)
        sh[:, :L - j] = p[:, j:]
        s &= sh
    return s


def to_buffy(f, T=14):
    """
    One learned formula in Buffy's bounded LTL (reads the monitors a5, ab and cenq of fq_conditions). A run
    must lie within boundaries 1..T, as in the traces: the model keeps running after T, so starts are
    clipped to T - k + 1.
    """
    out = []
    for g in f.split(" & "):
        g = g.strip()
        neg = g.startswith("~")
        g = g.lstrip("~")
        if g.startswith("run("):
            atom, k, iv = g[4:-1].split(",", 2)
            a, b = (int(x) for x in iv.strip("[)").split(","))
            b = min(b, T - int(k) + 2)
            p = PRED[atom]
            chain = p
            for _ in range(int(k) - 1):
                chain = f"{p} && X ({chain})"
            x = f"F<={b} (time >= {a} && time < {b} && {chain})"
        else:  # by(b,<=c) / by(b,>=c)
            b, rel = g[3:-1].split(",")
            x = f"G<={b} (time != {b} || fq.cenq {rel[:2]} {rel[2:]})"
        out.append(f"!({x})" if neg else f"({x})")
    return " && ".join(out)


def main():
    d = np.load(sys.argv[1])
    h5, hb, Q, W = d["h5"], d["hb"], d["q"], d["w"]
    min_p = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    n, T = h5.shape
    # boundary t (1..T) carries the arrivals of step t-1; index 0 (time 0) has none
    pad = lambda x: np.concatenate([np.full((n, 1), -1, dtype=x.dtype), x], axis=1)
    H5, HB = pad(h5), pad(hb)
    rng = np.random.default_rng(0)
    train = rng.random(n) < 0.5
    test = ~train
    pq = (W * Q).sum() / W.sum()
    print(f"sample {n} runs (weights for {int(d['runs'])}); P[Q] = {pq:.5f}")
    edges = [1, 5, 10, T + 1]
    intervals = [(a, b) for a in edges for b in edges if a < b]
    base = {}
    for fam, atoms in (("thin", THIN), ("bulk", BULK)):
        for (pn, fn), k, (a, b) in itertools.product(atoms.items(), [1, 2, 3, 4, 6, 9], intervals):
            p = fn(H5, HB) & (np.arange(T + 1)[None, :] >= 1)
            st = run_starts(p, k)[:, a:b].any(axis=1)
            base[(fam, f"run({pn},{k},[{a},{b}))")] = st
            base[(fam, f"~run({pn},{k},[{a},{b}))")] = ~st
    cen = np.cumsum(h5, axis=1)  # cenq at boundary t = cen[:, t-1]
    for b in range(2, T + 1):
        for c in range(0, 4 * b + 1):
            base[("thin", f"by({b},<={c})")] = cen[:, b - 1] <= c
            base[("thin", f"by({b},>={c})")] = cen[:, b - 1] >= c

    def score(v, idx):
        w = W[idx]
        pc = (w * v[idx]).sum() / w.sum()
        return pc, ((w * (v & Q)[idx]).sum() / (w * v[idx]).sum()) if pc > 0 else float("nan")

    singles = []
    for (fam, f), v in base.items():
        pc, pqc = score(v, train)
        if min_p <= pc <= 0.98:
            singles.append((pqc, pc, fam, f, v))
    singles.sort(key=lambda r: -r[0])
    cand = singles[:80] + singles[-40:]
    rows = list(singles)
    for (q1, p1, f1, n1, v1), (q2, p2, f2, n2, v2) in itertools.combinations(cand, 2):
        v = v1 & v2
        pc, pqc = score(v, train)
        if pc >= min_p:
            rows.append((pqc, pc, "thin" if f1 == f2 == "thin" else "bulk", f"{n1} & {n2}", v))
    out = []
    for title, sel in (("dangerous", sorted(rows, key=lambda r: -r[0])), ("protective", sorted(rows, key=lambda r: r[0]))):
        for fam in ("thin", "bulk"):
            print(f"\n{title}, {fam}-flow conditions, P[c] >= {min_p}; train | held-out")
            for pqc, pc, fm, f, v in [r for r in sel if r[2] == fam][:top]:
                pc2, pqc2 = score(v, test)
                print(f"  P[c]={pc:.3f} P[Q|c]={pqc:.4f} lift={pqc / pq:.1f} | P[c]={pc2:.3f} P[Q|c]={pqc2:.4f}   {f}")
                out.append({"kind": title, "family": fam, "formula": f, "buffy": to_buffy(f), "train": [pc, pqc],
                            "heldout": [pc2, pqc2]})
    # the draft's hand-picked conditions, for comparison
    print("\nthe draft's conditions:")
    for f in ("by(5,<=1)", "by(11,>=5)"):
        v = base[("thin", f)]
        print(f"  P[c]={score(v, test)[0]:.3f} P[Q|c]={score(v, test)[1]:.4f}   {f}")
    if len(sys.argv) > 4:
        json.dump({"PQ": pq, "conditions": out}, open(sys.argv[4], "w"), indent=1)


if __name__ == "__main__":
    main()
