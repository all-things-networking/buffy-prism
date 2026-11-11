"""
Learn conditions on the PFC model's input that make Q = "U (which never touches switch 2) is blocked in at
least BLK of the window's steps" likely or unlikely. Histories from pfc_histories.py (weighted sample).

Formula families over time-step boundaries 1..T (boundary t carries step t-1's arrivals):
  run(p, k, [a, b)), ~run(...)   k consecutive steps whose arrivals satisfy p, starting in [a, b)
  inc(b, <= c), inc(b, >= c)      incast packets by boundary b (monitor cb)
  and conjunctions of two.
Atoms: incast burst none / >= 1 / >= 2 / = 3 ("incast" family: one source, certified exactly by
--condition-on); culprit arrival / none ("culprit" family: a second source, certified by rejection).

Usage: python learn_pfc.py histories.npz [min_p] [top] [blk]
"""
import itertools
import sys

import numpy as np

INC = {"b0": lambda b, c: b == 0, "b1": lambda b, c: b >= 1, "b2": lambda b, c: b >= 2, "b3": lambda b, c: b == 3}
CUL = {"c1": lambda b, c: c == 1, "c0": lambda b, c: c == 0}
PRED = {"b0": "pfc.bl == 0", "b1": "pfc.bl >= 1", "b2": "pfc.bl >= 2", "b3": "pfc.bl == 3"}
EDGES = [1, 11, 21, 31, 41, 51, 61]


def run_starts(p, k):
    n, L = p.shape
    s = np.ones((n, L), dtype=bool)
    for j in range(k):
        sh = np.zeros_like(p)
        sh[:, :L - j] = p[:, j:]
        s &= sh
    return s


def to_buffy(f, T=60):
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
        else:
            b, rel = g[4:-1].split(",")
            x = f"G<={b} (time != {b} || pfc.cb {rel[:2]} {rel[2:]})"
        out.append(f"!({x})" if neg else f"({x})")
    return " && ".join(out)


def main():
    d = np.load(sys.argv[1])
    b, c, u, W = d["b"], d["c"], d["u"], d["w"]
    min_p = float(sys.argv[2]) if len(sys.argv) > 2 else 0.05
    top = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    blk = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    Q = u >= blk
    n, T = b.shape
    pad = lambda x: np.concatenate([np.full((n, 1), -1, dtype=x.dtype), x], axis=1)
    Bp, Cp = pad(b), pad(c)
    valid = np.arange(T + 1)[None, :] >= 1
    train = np.random.default_rng(0).random(n) < 0.5
    test = ~train
    pq = (W * Q).sum() / W.sum()
    print(f"sample {n} runs (weights for {int(d['runs'])}); P[Q] = {pq:.5f}")
    intervals = [(a, e) for a in EDGES for e in EDGES if a < e]
    base = {}
    for fam, atoms in (("incast", INC), ("culprit", CUL)):
        for (pn, fn), k, (a, e) in itertools.product(atoms.items(), [1, 2, 3, 4, 6, 8], intervals):
            st = run_starts(fn(Bp, Cp) & valid, k)[:, a:e].any(axis=1)
            base[(fam, f"run({pn},{k},[{a},{e}))")] = st
            base[(fam, f"~run({pn},{k},[{a},{e}))")] = ~st
    cb = np.cumsum(b, axis=1)
    for e in (10, 20, 30, 40, 50, 60):
        for k in range(0, 3 * e + 1, 2):
            base[("incast", f"inc({e},<={k})")] = cb[:, e - 1] <= k
            base[("incast", f"inc({e},>={k})")] = cb[:, e - 1] >= k

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
            rows.append((pqc, pc, "incast" if f1 == f2 == "incast" else "culprit", f"{n1} & {n2}", v))
    for title, sel in (("dangerous", sorted(rows, key=lambda r: -r[0])), ("protective", sorted(rows, key=lambda r: r[0]))):
        for fam in ("incast", "culprit"):
            print(f"\n{title}, {fam} conditions, P[c] >= {min_p}; train | held-out")
            for pqc, pc, fm, f, v in [r for r in sel if r[2] == fam][:top]:
                pc2, pqc2 = score(v, test)
                print(f"  P[c]={pc:.3f} P[Q|c]={pqc:.4f} lift={pqc / pq:.1f} | P[c]={pc2:.3f} P[Q|c]={pqc2:.4f}   {f}")


if __name__ == "__main__":
    main()
