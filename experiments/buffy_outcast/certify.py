"""
Certify learned conditions on the compiled Buffy model, from fresh runs (a seed not used for learning).
Reports P[c], P[Q | c] with 95% Clopper-Pearson intervals, and P[Q].

Two encodings of a condition c in a copy of buffy/examples/jani/outcast.buffy:
  ltl  - the query `P=? [ Q ] given c` with c in Buffy's bounded LTL; Buffy compiles c and Q && c into
         deterministic monitors by formula progression, one per subformula when a single monitor of
         the conjunction would be too large (design decision 48).
  mon  - each run(p, k, [a, b)) in c becomes two monitor variables updated in the method: the length of
         the current run of p (saturating at k) and a sticky flag "a run of k started in [a, b)". c is
         then a state predicate at time T. Same meaning, a few states per subformula.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_outcast/certify.py conds.json runs seed "NA=2 ..." [i,j,...] [ltl|mon]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from src.netmdp.hyptest.intervals import clopper_pearson
from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "buffy/examples/jani/outcast.buffy"


def q_formula(qspec):
    kind, val = qspec.split(":")
    if kind == "starveB":
        return f"F<=T (time == T && outcast.got[NA] <= {val})"
    raise ValueError(qspec)


# The atoms as expressions over the step's new values of the monitors aA, aB (assigned in the method).
ATOM = {"aA": "aA == 1", "aB": "aB == 1", "!aA": "aA == 0", "!aB": "aB == 0", "aA&aB": "aA == 1 & aB == 1",
        "aB&!aA": "aB == 1 & aA == 0", "aA&!aB": "aA == 1 & aB == 0", "!aA&!aB": "aA == 0 & aB == 0"}
INIT = {"aA": 0, "aB": 0}   # the atoms' values in the initial state (time 0)


def parse(g):
    neg = g.startswith("~")
    atom, k, iv = g.lstrip("~")[4:-1].split(",", 2)
    a, b = (int(x) for x in iv.strip("[)").split(","))
    return neg, atom, int(k), a, b


def holds_init(atom):
    return eval(ATOM[atom].replace("&", " and ").replace("aA", str(INIT["aA"])).replace("aB", str(INIT["aB"])))


def with_monitors(prog, conds, pick):
    """ Adds the run monitors of the picked conditions; returns the program and each condition's predicate. """
    decls, upds, preds, seen = [], [], {}, {}
    for i in pick:
        parts = []
        for g in conds["conditions"][i]["formula"].split(" & "):
            neg, atom, k, a, b = parse(g.strip())
            key = (atom, k, a, b)
            if key not in seen:
                n = len(seen)
                seen[key] = n
                h0 = holds_init(atom)
                hit0 = "true" if (h0 and k == 1 and a == 0 < b) else "false"
                decls.append(f"    //@ monitor int<0..{k}> rl{n} = {1 if h0 else 0};")
                decls.append(f"    //@ monitor bool hit{n} = {hit0};")
                # the boundary being computed is time + 1; a run of k ending there started at time + 2 - k
                upds.append(f"    //@ rl{n} = ({ATOM[atom]}) ? min({k}, rl{n} + 1) : 0;")
                upds.append(f"    //@ if (rl{n} >= {k} & time + 2 - {k} >= {a} & time + 2 - {k} < {b}) hit{n} = true;")
            n = seen[key]
            parts.append(f"{'!' if neg else ''}outcast.hit{n}")
        preds[i] = "(" + " && ".join(parts) + ")"
    lines = prog.splitlines()
    out = []
    for l in lines:
        out.append(l)
        if l.strip() == "//@ monitor int<0..1> aB;":
            out += decls
        if l.strip() == "//@ aB = fb != -1 ? 1 : 0;":
            out += upds
    return "\n".join(out), preds


def main():
    conds = json.load(open(sys.argv[1]))
    runs, seed, defs = int(sys.argv[2]), int(sys.argv[3]), sys.argv[4].split()
    pick = [int(x) for x in sys.argv[5].split(",")] if len(sys.argv) > 5 else range(len(conds["conditions"]))
    enc = sys.argv[6] if len(sys.argv) > 6 else "mon"
    prog = "\n".join(l for l in SRC.read_text().splitlines() if not l.startswith(("query", "reward")))
    q = q_formula(conds["Q"])
    if enc == "mon":
        prog, preds = with_monitors(prog, conds, pick)
    prog += f"\nquery q: P=? [ {q} ];\n"
    for i in pick:
        if enc == "ltl":
            prog += f"query c{i}: P=? [ {q} ] given {conds['conditions'][i]['buffy']};\n"
        else:
            qs = q.replace("(time == T &&", f"(time == T && {preds[i]} &&")
            prog += f"query c{i}_joint: P=? [ {qs} ];\nquery c{i}_given: P=? [ F<=T (time == T && {preds[i]}) ];\n"
    with tempfile.TemporaryDirectory() as d:
        b, j = Path(d) / "oc.buffy", Path(d) / "oc.jani"
        b.write_text(prog)
        cmd = [str(ROOT / "buffy/build/buffyc-mc"), str(b), "--stop-at-horizon", "-o", str(j)]
        for kv in defs:
            cmd += ["-D", kv]
        subprocess.run(cmd, check=True, timeout=600)
        model = json.loads(j.read_text())
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {}
    for p in model["properties"]:
        e = p["expression"]["values"]["exp"]["right"]
        obs[p["name"]] = {"op": "ite", "if": e, "then": 1, "else": 0}
    r = JaniModel(model, observables=obs).simulate_rewards(runs, T, None, seed=seed)
    hit = {n: (r.state_cumulative[n] > 0) | (r.final[n] > 0) for n in obs}
    pq = hit["q"].mean()
    lo, hi = clopper_pearson(int(hit["q"].sum()), runs, 0.95)
    print(f"{' '.join(defs)}  [{enc}]  runs={runs} seed={seed}  P[Q]={pq:.4f} [{lo:.4f},{hi:.4f}]")
    for i in pick:
        c, qc = hit[f"c{i}_given"], hit[f"c{i}_joint"]
        n, k = int(c.sum()), int(qc.sum())
        clo, chi = clopper_pearson(k, n, 0.95) if n else (float("nan"), float("nan"))
        cd = conds["conditions"][i]
        print(f"  c{i} [{cd['kind']}] P[c]={c.mean():.4f}  P[Q|c]={k / max(n, 1):.4f} [{clo:.4f},{chi:.4f}]  "
              f"(learned: P[c]={cd['heldout'][0]:.3f} P[Q|c]={cd['heldout'][1]:.3f})  {cd['formula']}")


if __name__ == "__main__":
    main()
