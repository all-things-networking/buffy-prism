"""
Learn conditions on the LLM scheduler's arrivals (llm_histories.py) that make a bad event Q for the tracked
request likely or unlikely:
  evicted   - evicted at least once
  wait<g>   - its worst gap between tokens (or before the first) is at least g iterations

Formula families over time-step boundaries 1..T (boundary t carries the draw of iteration t-1; the tracked
request arrives in iteration T_V, so boundaries 1..T_V are "before it"):
  run(p, k, [a, b)), ~run(...)   k consecutive iterations whose draw satisfies p, starting in [a, b)
  lp(b, <= c), lp(b, >= c)        long-prompt draws by boundary b (monitor clp)
  lo(b, <= c), lo(b, >= c)        long-output draws by boundary b (monitor clo)
  conjunctions of two.
Atoms on the draw (0 none, 1 short/short, 2 short prompt/long output, 3 long/short, 4 long/long):
  none, any, LP (long prompt), LO (long output), LL (both long), SS (both short), SP (short prompt).
Every condition reads only the arrival draws, so --condition-on certifies it exactly.

Usage: python learn_llm.py histories.npz Q [min_p] [top] [out.json]
"""
import itertools
import json
import sys

import numpy as np

ATOMS = {"none": lambda h: h == 0, "any": lambda h: h >= 1, "LP": lambda h: h >= 3,
         "LO": lambda h: (h == 2) | (h == 4), "LL": lambda h: h == 4, "SS": lambda h: h == 1,
         "SP": lambda h: (h == 1) | (h == 2)}
PRED = {"none": "worker.sh == 0", "any": "worker.sh >= 1", "LP": "worker.sh >= 3",
        "LO": "(worker.sh == 2 || worker.sh == 4)", "LL": "worker.sh == 4", "SS": "worker.sh == 1",
        "SP": "(worker.sh == 1 || worker.sh == 2)"}
EDGES = [1, 3, 6, 11, 21, 41]


def run_starts(p, k):
    n, L = p.shape
    s = np.ones((n, L), dtype=bool)
    for j in range(k):
        sh = np.zeros_like(p)
        sh[:, :L - j] = p[:, j:]
        s &= sh
    return s


def to_buffy(f, T=40):
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
        else:  # lp(b,<=c) / lo(b,>=c)
            var = {"lp": "worker.clp", "lo": "worker.clo"}[g[:2]]
            b, rel = g[3:-1].split(",")
            x = f"G<={b} (time != {b} || {var} {rel[:2]} {rel[2:]})"
        out.append(f"!({x})" if neg else f"({x})")
    return " && ".join(out)


def main():
    d = np.load(sys.argv[1])
    h, pre, gap, W = d["h"], d["pre"], d["gap"], d["w"]
    qs = sys.argv[2]
    Q = pre >= 1 if qs == "evicted" else gap >= int(qs[4:])
    min_p = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
    top = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    n, T = h.shape
    H = np.concatenate([np.full((n, 1), -1, dtype=h.dtype), h], axis=1)
    valid = np.arange(T + 1)[None, :] >= 1
    train = np.random.default_rng(0).random(n) < 0.5
    test = ~train
    pq = (W * Q).sum() / W.sum()
    print(f"sample {n} runs (weights for {int(d['runs'])}); Q = {qs}: P[Q] = {pq:.4f}")
    intervals = [(a, b) for a in EDGES for b in EDGES if a < b]
    base = {}
    for (pn, fn), k, (a, b) in itertools.product(ATOMS.items(), [1, 2, 3, 4, 6], intervals):
        st = run_starts(fn(H) & valid, k)[:, a:b].any(axis=1)
        base[f"run({pn},{k},[{a},{b}))"] = st
        base[f"~run({pn},{k},[{a},{b}))"] = ~st
    clp, clo = np.cumsum(h >= 3, axis=1), np.cumsum((h == 2) | (h == 4), axis=1)
    for name, c in (("lp", clp), ("lo", clo)):
        for b in (3, 5, 6, 8, 10, 15, 20, 30):
            for k in range(0, b + 1):
                base[f"{name}({b},<={k})"] = c[:, b - 1] <= k
                base[f"{name}({b},>={k})"] = c[:, b - 1] >= k

    def score(v, idx):
        w = W[idx]
        pc = (w * v[idx]).sum() / w.sum()
        return pc, ((w * (v & Q)[idx]).sum() / (w * v[idx]).sum()) if pc > 0 else float("nan")

    singles = []
    for f, v in base.items():
        pc, pqc = score(v, train)
        if min_p <= pc <= 0.98:
            singles.append((pqc, pc, f, v))
    singles.sort(key=lambda r: -r[0])
    cand = singles[:80] + singles[-60:]
    rows = list(singles)
    for (q1, p1, f1, v1), (q2, p2, f2, v2) in itertools.combinations(cand, 2):
        v = v1 & v2
        pc, pqc = score(v, train)
        if pc >= min_p:
            rows.append((pqc, pc, f"{f1} & {f2}", v))
    out = []
    for title, sel in (("dangerous", sorted(rows, key=lambda r: -r[0])), ("protective", sorted(rows, key=lambda r: r[0]))):
        print(f"\n{title}, P[c] >= {min_p}; train | held-out")
        for pqc, pc, f, v in sel[:top]:
            pc2, pqc2 = score(v, test)
            print(f"  P[c]={pc:.3f} P[Q|c]={pqc:.4f} lift={pqc / pq:.2f} | P[c]={pc2:.3f} P[Q|c]={pqc2:.4f}   {f}")
            out.append({"kind": title, "formula": f, "buffy": to_buffy(f, T), "train": [pc, pqc], "heldout": [pc2, pqc2]})
    if len(sys.argv) > 5:
        json.dump({"Q": qs, "PQ": pq, "conditions": out}, open(sys.argv[5], "w"), indent=1)


if __name__ == "__main__":
    main()
