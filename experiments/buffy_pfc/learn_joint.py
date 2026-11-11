"""
Joint conditions on the PFC model's input: formulas over all four random sources (incast bursts, the
culprit C, and the victims' own sends U and V), which Buffy's --target native conditions on jointly. Q = U
is blocked in at least BLK of the window's steps. Histories from pfc_histories.py (weighted sample).

A short condition cannot be mild and make a rare Q likely: P(Q | A) <= P(Q) / P(A). So the question here is
how much of Q a short condition explains: its precision P(Q | A) at a given P(A), and its recall P(A | Q).

Formula families over time-step boundaries 1..T (boundary t carries step t-1's arrivals):
  run(p, k, [a, b)), ~run(...)   k consecutive steps whose arrivals satisfy p, starting in [a, b)
  inc / cc / cu / cv(b, <= n | >= n)   incast packets / culprit, U, V sends by boundary b
Atoms p: b0 b1 b2 b3 (incast none / >= 1 / >= 2 / = 3), c1 c0, u1 u0, v1 v0. Conditions: single formulas,
and conjunctions of two and three (a beam over the 40 best by precision of each source), each with P(A) >= min_p on the
training half; reported with the held-out half.

Usage: python learn_joint.py histories.npz [min_p ...] [--top n] [--blk n]
"""
import itertools
import sys

import numpy as np

EDGES = [1, 11, 21, 31, 41, 51, 61]
ATOMS = {"b0": ("b", lambda x: x == 0), "b1": ("b", lambda x: x >= 1), "b2": ("b", lambda x: x >= 2),
         "b3": ("b", lambda x: x == 3), "c1": ("c", lambda x: x == 1), "c0": ("c", lambda x: x == 0),
         "u1": ("hu", lambda x: x == 1), "u0": ("hu", lambda x: x == 0),
         "v1": ("hv", lambda x: x == 1), "v0": ("hv", lambda x: x == 0)}
PRED = {"b0": "pfc.bl == 0", "b1": "pfc.bl >= 1", "b2": "pfc.bl >= 2", "b3": "pfc.bl == 3",
        "c1": "pfc.cl == 1", "c0": "pfc.cl == 0", "u1": "pfc.lu == 1", "u0": "pfc.lu == 0",
        "v1": "pfc.lv == 1", "v0": "pfc.lv == 0"}
COUNT = {"inc": ("b", "pfc.cb"), "cc": ("c", "pfc.cc"), "cu": ("hu", "pfc.cu"), "cv": ("hv", "pfc.cv")}
SOURCE = {"b": "incast", "c": "culprit", "hu": "U", "hv": "V"}


def run_starts(p, k):
    n, L = p.shape
    s = np.ones((n, L), dtype=bool)
    for j in range(k):
        sh = np.zeros_like(p)
        sh[:, :L - j] = p[:, j:]
        s &= sh
    return s


def to_buffy(f, T=60):
    """A condition in this notation as a Buffy bounded-LTL formula over pfc_conditions.buffy's monitors."""
    out = []
    for g in f.split(" & "):
        g = g.strip()
        neg = g.startswith("~")
        g = g.lstrip("~")
        if g.startswith("run("):
            atom, k, iv = g[4:-1].split(",", 2)
            a, b = (int(x) for x in iv.strip("[)").split(","))
            b = min(b, T - int(k) + 2)
            chain = PRED[atom]
            for _ in range(int(k) - 1):
                chain = f"{PRED[atom]} && X ({chain})"
            x = f"F<={b} (time >= {a} && time < {b} && {chain})"
        else:
            name, rest = g.split("(", 1)
            b, rel = rest[:-1].split(",")
            x = f"G<={b} (time != {b} || {COUNT[name][1]} {rel[:2]} {rel[2:]})"
        out.append(f"!({x})" if neg else f"({x})")
    return " && ".join(out)


def sources_of(f):
    s = set()
    for g in f.split(" & "):
        g = g.strip().lstrip("~")
        s.add(ATOMS[g[4:6]][0] if g.startswith("run(") else COUNT[g.split("(")[0]][0])
    return s


def features(d):
    n, T = d["b"].shape
    pad = lambda x: np.concatenate([np.full((n, 1), -1, dtype=x.dtype), x], axis=1)
    H = {k: pad(d[k]) for k in ("b", "c", "hu", "hv")}
    valid = np.arange(T + 1)[None, :] >= 1
    intervals = [(a, e) for a in EDGES for e in EDGES if a < e]
    for (pn, (src, fn)), k, (a, e) in itertools.product(ATOMS.items(), [1, 2, 3, 4, 6, 8], intervals):
        st = run_starts(fn(H[src]) & valid, k)[:, a:e].any(axis=1)
        yield f"run({pn},{k},[{a},{e}))", st
        yield f"~run({pn},{k},[{a},{e}))", ~st
    for name, (src, _) in COUNT.items():
        cum = np.cumsum(d[src], axis=1)
        step = 2 if src == "b" else 1
        for e in (10, 20, 30, 40, 50, 60):
            top = (3 if src == "b" else 1) * e
            for k in range(0, top + 1, step):
                yield f"{name}({e},<={k})", cum[:, e - 1] <= k
                yield f"{name}({e},>={k})", cum[:, e - 1] >= k


def main():
    args = [a for a in sys.argv[1:]]
    opt = lambda name, dflt: int(args[args.index(name) + 1]) if name in args else dflt
    top, blk = opt("--top", 8), opt("--blk", 10)
    for name in ("--top", "--blk"):
        if name in args:
            i = args.index(name)
            del args[i:i + 2]
    d = np.load(args[0])
    min_ps = [float(x) for x in args[1:]] or [0.01, 0.003, 0.001]
    W, Q = d["w"], d["u"] >= blk
    n = len(W)
    train = np.random.default_rng(0).random(n) < 0.5
    test = ~train
    pq = (W * Q).sum() / W.sum()
    print(f"sample {n} runs (weights for {int(d['runs'])}); P[Q] = {pq:.5f}; {int(Q.sum())} runs with Q")
    # Single formulas: statistics on the training half, vectors kept bit-packed (about 4,000 x n bits).
    # Cached next to the histories (<histories>.feat<blk>.npz).
    cache = args[0][:-4] + f".feat{blk}.npz"
    try:
        z = np.load(cache, allow_pickle=False)
        names, packed, pa_all, jq_all = list(z["names"]), list(z["packed"]), z["pa"], z["jq"]
    except OSError:
        names, packed, pa_l, jq_l = [], [], [], []
        Wt, Qt = W[train], Q[train]
        tot = Wt.sum()
        for f, v in features(d):
            names.append(f)
            packed.append(np.packbits(v))
            pa_l.append((Wt * v[train]).sum() / tot)
            jq_l.append((Wt * (v[train] & Qt)).sum() / tot)
        pa_all, jq_all = np.array(pa_l), np.array(jq_l)
        np.savez(cache, names=np.array(names), packed=np.stack(packed), pa=pa_all, jq=jq_all)
    col = lambda i: np.unpackbits(packed[i], count=n).astype(bool)
    print(f"{len(names)} single formulas")

    def score(v, idx):
        w = W[idx]
        pa = (w * v[idx]).sum() / w.sum()
        if pa <= 0:
            return 0.0, float("nan"), 0.0
        prec = (w * (v & Q)[idx]).sum() / (w * v[idx]).sum()
        rec = (w * (v & Q)[idx]).sum() / (w * Q[idx]).sum()
        return pa, prec, rec

    for min_p in min_ps:
        ok = (pa_all >= min_p) & (pa_all <= 0.98)
        prec = np.where(ok, jq_all / np.maximum(pa_all, 1e-300), -1)
        order = np.argsort(-prec)
        # the beam: the best 40 single formulas of each source (so that every source can take part)
        fam = [next(iter(sources_of(f))) for f in names]
        beam = []
        for src in ("b", "c", "hu", "hv"):
            beam += [int(i) for i in order if prec[i] > 0 and fam[i] == src][:40]
        beam.sort(key=lambda i: -prec[i])
        C = {i: col(i) for i in beam}
        rows = [(prec[i], names[i], C[i]) for i in beam[:top * 4]]
        pairs = []
        for i, j in itertools.combinations(beam, 2):
            v = C[i] & C[j]
            pa, pr, _ = score(v, train)
            if pa >= min_p:
                pairs.append((pr, f"{names[i]} & {names[j]}", v))
        pairs.sort(key=lambda r: -r[0])
        rows += pairs[:top * 4]
        triples = {}
        for pr2, f2, v2 in pairs[:60]:
            for i in beam[:100]:
                if names[i] in f2.split(" & "):
                    continue
                v = v2 & C[i]
                pa, pr, _ = score(v, train)
                if pa >= min_p:
                    key = " & ".join(sorted(f2.split(" & ") + [names[i]]))
                    triples[key] = (pr, key, v)
        allrows = [(prec[i], names[i], C[i]) for i in beam] + pairs + list(triples.values())
        rows += sorted(triples.values(), key=lambda r: -r[0])[:top * 4]
        rows.sort(key=lambda r: -r[0])
        best = {}
        for pr, f, v in allrows:
            key = "+".join(SOURCE[s] for s in sorted(sources_of(f)))
            if key not in best or pr > best[key][0]:
                best[key] = (pr, f, v)
        print(f"\n#### P(A) >= {min_p}: the best condition of each set of sources; train | held-out")
        for key, (pr, f, v) in sorted(best.items(), key=lambda kv: -kv[1][0]):
            pa, pr, rc = score(v, train)
            pa2, pr2, rc2 = score(v, test)
            print(f"  P(A)={pa:.4f} P(Q|A)={pr:.4f} P(A|Q)={rc:.3f} | P(A)={pa2:.4f} P(Q|A)={pr2:.4f} P(A|Q)={rc2:.3f}"
                  f"  [{key}]  {f}")
        print(f"\n#### P(A) >= {min_p} (precision at most P[Q] / P(A) = {min(1, pq / min_p):.3f}); train | held-out")
        seen = set()
        shown = 0
        for _, f, v in rows:
            if f in seen:
                continue
            seen.add(f)
            pa, pr, rc = score(v, train)
            pa2, pr2, rc2 = score(v, test)
            srcs = "+".join(SOURCE[s] for s in sorted(sources_of(f)))
            print(f"  P(A)={pa:.4f} P(Q|A)={pr:.4f} P(A|Q)={rc:.3f} | P(A)={pa2:.4f} P(Q|A)={pr2:.4f} P(A|Q)={rc2:.3f}"
                  f"  [{srcs}]  {f}")
            shown += 1
            if shown >= top:
                break


if __name__ == "__main__":
    main()
