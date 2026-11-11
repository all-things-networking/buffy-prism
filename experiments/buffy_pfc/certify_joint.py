"""
Certify conditions on the PFC model's input over any of its four random sources (incast, culprit, U, V):
`buffyc-mc --target native --condition-on` conditions the sources the condition reads jointly, P(A) is exact
(the simulator's on-demand h), and P(Q | A) is estimated from conditioned runs that all satisfy A (95%
Clopper-Pearson). With `--reject n k` the first k conditions are also estimated by rejection from n
unconditioned runs (_joint / _given), as a cross-check.

Conditions in learn_joint.py's notation, in a file of lines `name | formula`.
Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_pfc/certify_joint.py conds.txt blkU<n> "PB=0.3 ..." runs seed [--reject n k]
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from learn_joint import to_buffy, sources_of, SOURCE  # noqa: E402
from src.netmdp.hyptest.intervals import clopper_pearson  # noqa: E402
from src.netmdp.sim.jani_native import JaniModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BUFFYC = str(ROOT / "buffy/build/buffyc-mc")


def hits(model, names, runs, seed, jm=None):
    T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    obs = {p["name"]: {"op": "ite", "if": p["expression"]["values"]["exp"]["right"], "then": 1, "else": 0}
           for p in model["properties"] if p["name"] in names}
    jm = JaniModel(model, observables=obs)
    tot = {k: 0 for k in obs}
    done, b = 0, 0
    while done < runs:
        n = min(500_000, runs - done)
        r = jm.simulate_rewards(n, T, None, seed=seed * 1000 + b)
        for k in obs:
            tot[k] += int(((r.state_cumulative[k] > 0) | (r.final[k] > 0)).sum())
        done, b = done + n, b + 1
    return tot, jm


def main():
    conds = [tuple(x.strip() for x in l.split("|", 1)) for l in open(sys.argv[1]) if "|" in l and not l.startswith("#")]
    qs, defs, runs, seed = sys.argv[2], sys.argv[3].split(), int(sys.argv[4]), int(sys.argv[5])
    Q = f"F<=T (time == T && pfc.uBlk >= {int(qs[4:])})"   # qs = blkU<n>
    reject = int(sys.argv[sys.argv.index("--reject") + 1]) if "--reject" in sys.argv else 0
    nrej = int(sys.argv[sys.argv.index("--reject") + 2]) if "--reject" in sys.argv else 0
    base = (Path(__file__).parent / "pfc_conditions.buffy").read_text()
    prog = base + f"query q: P=? [ {Q} ];\n" + "".join(f"query {n}: P=? [ {Q} ] given {to_buffy(f)};\n" for n, f in conds)
    dflags = [x for kv in defs for x in ("-D", kv)]
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "pfc.buffy"
        src.write_text(prog)
        out = Path(d) / "pfc.jani"
        subprocess.run([BUFFYC, str(src), *dflags, "--target", "native", "--stop-at-horizon", "-o", str(out)],
                       check=True, timeout=600)
        plain = json.loads(out.read_text())
        names = {"q"} | ({f"{n}_{s}" for n, _ in conds[:nrej] for s in ("joint", "given")} if reject else set())
        nq = reject or runs
        rej, _ = hits(plain, names, nq, seed + 1)
        h = rej["q"]
        lo, hi = clopper_pearson(h, nq, 0.95)
        print(f"{qs}, {' '.join(defs)}: P[Q] = {h / nq:.4g} [{lo:.4g}, {hi:.4g}]  ({nq} runs)", flush=True)
        for i, (n, f) in enumerate(conds):
            srcs = "+".join(SOURCE[s] for s in sorted(sources_of(f)))
            cout = Path(d) / f"pfc_{n}.jani"
            t0 = time.time()
            r = subprocess.run([BUFFYC, str(src), *dflags, "--target", "native", "--stop-at-horizon", "--condition-on", n,
                                "-o", str(cout)], capture_output=True, text=True, timeout=600)
            if r.returncode != 0:
                print(f"  {n}: compile error: {r.stderr.strip()}", flush=True)
                continue
            m = json.loads(cout.read_text())
            t1 = time.time()
            k, jm = hits(m, {n}, runs, seed)
            k = k[n]
            pa, ns = jm.condition_probability(), jm.condition_states()
            clo, chi = clopper_pearson(k, runs, 0.95)
            line = (f"  {n} [{srcs}]: P(A) = {pa:.4g} (exact, {ns} input states)  P(Q|A) = {k / runs:.4g} "
                    f"[{clo:.4g}, {chi:.4g}]  lift {k / runs / max(h / nq, 1e-12):.0f}  P(A|Q) ~ {pa * k / runs / max(h / nq, 1e-12):.3f}"
                    f"  ({t1 - t0:.1f} s compile, {time.time() - t1:.0f} s build + runs)")
            if i < nrej and reject:
                j, g = rej[f"{n}_joint"], rej[f"{n}_given"]
                line += f"  | rejection: {j}/{g} = {j / max(g, 1):.4g} (P(A) ~ {g / reject:.4g})"
            print(line + f"   {f}", flush=True)


if __name__ == "__main__":
    main()
