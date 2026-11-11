"""
Certify conditions on the LLM scheduler's arrivals with --condition-on: for each condition A, the
compiler conditions the arrival source on A exactly and reports P(A) exactly; the
native simulator estimates P(Q | A) from runs that all satisfy A (95% Clopper-Pearson). With `--reject n`
the first conditions are also estimated the old way, as _joint / _given from n unconditioned runs.

Conditions are given in learn_llm.py's notation in a file of lines `name | formula`.
Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_llm/certify_llm.py conds.txt Q "R=8 ..." runs seed [--reject n k]
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from learn_llm import to_buffy  # noqa: E402
from src.netmdp.hyptest.intervals import clopper_pearson  # noqa: E402
from src.netmdp.sim.jani_native import JaniModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BUFFYC = str(ROOT / "buffy/build/buffyc-mc")
QF = {"evicted": "F<=T worker.v_preempts >= 1"}


def hits(model, names, runs, seed):
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {}
    for p in model["properties"]:
        if p["name"] in names:
            obs[p["name"]] = {"op": "ite", "if": p["expression"]["values"]["exp"]["right"], "then": 1, "else": 0}
    jm = JaniModel(model, observables=obs)
    tot = {n: 0 for n in obs}
    done, b = 0, 0
    while done < runs:
        n = min(1_000_000, runs - done)
        r = jm.simulate_rewards(n, T, None, seed=seed * 1000 + b)
        for k in obs:
            tot[k] += int(((r.state_cumulative[k] > 0) | (r.final[k] > 0)).sum())
        done, b = done + n, b + 1
    return tot


def main():
    conds = [tuple(x.strip() for x in l.split("|", 1)) for l in open(sys.argv[1]) if "|" in l and not l.startswith("#")]
    qs, defs, runs, seed = sys.argv[2], sys.argv[3].split(), int(sys.argv[4]), int(sys.argv[5])
    Q = QF.get(qs) or f"F<=T worker.v_maxgap >= {int(qs[4:])}"
    reject = int(sys.argv[sys.argv.index("--reject") + 1]) if "--reject" in sys.argv else 0
    nrej = int(sys.argv[sys.argv.index("--reject") + 2]) if "--reject" in sys.argv else 0
    base = (Path(__file__).parent / "llm_conditions.buffy").read_text()
    prog = base + f"query q: P=? [ {Q} ];\n" + "".join(f"query {n}: P=? [ {Q} ] given {to_buffy(f)};\n" for n, f in conds)
    dflags = [x for kv in defs for x in ("-D", kv)]
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "llm.buffy"
        src.write_text(prog)
        out = Path(d) / "llm.jani"
        subprocess.run([BUFFYC, str(src), *dflags, "--stop-at-horizon", "-o", str(out)], check=True, timeout=600)
        plain = json.loads(out.read_text())
        rej = {}
        if reject:
            names = ["q"] + [f"{n}_{s}" for n, _ in conds[:nrej] for s in ("joint", "given")]
            rej = hits(plain, set(names), reject, seed + 1)
        h = hits(plain, {"q"}, runs, seed)["q"] if not reject else rej["q"]
        nq = reject or runs
        lo, hi = clopper_pearson(h, nq, 0.95)
        print(f"{qs}, {' '.join(defs)}: P[Q] = {h / nq:.4g} [{lo:.4g}, {hi:.4g}]  ({nq} runs)", flush=True)
        for i, (n, f) in enumerate(conds):
            cout = Path(d) / f"llm_{n}.jani"
            r = subprocess.run([BUFFYC, str(src), *dflags, "--stop-at-horizon", "--condition-on", n, "-o", str(cout)],
                               capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                print(f"  {n}: compile error: {r.stderr.strip()}")
                continue
            m = json.loads(cout.read_text())
            pa = float(re.search(r"P\(condition\) = ([0-9.e+-]+)", cout.read_text()).group(1))
            k = hits(m, {n}, runs, seed)[n]
            clo, chi = clopper_pearson(k, runs, 0.95)
            line = f"  {n}: P(A) = {pa:.4g} (exact)  P(Q|A) = {k / runs:.4g} [{clo:.4g}, {chi:.4g}]  lift {k / runs / max(h / nq, 1e-12):.0f}"
            if i < nrej and reject:
                j, g = rej[f"{n}_joint"], rej[f"{n}_given"]
                line += f"  | rejection: {j}/{g} = {j / max(g, 1):.4g} (P(A) ~ {g / reject:.4g})"
            print(line + f"   {f}", flush=True)


if __name__ == "__main__":
    main()
