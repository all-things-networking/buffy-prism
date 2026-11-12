"""
Axis 2 of the fabric scaling study: the horizon. One fabric size, a query round every PERIOD steps, horizons T from
one round to about 10^4 steps. For each T, in its own process, one after the other:
- compile and build (the horizon changes only the bounds, so this cost does not depend on T);
- simulate as many runs as fit in `budget` seconds (at least 100), and report the cost per run and per step;
- P_T = P[some round within T in which the victim loses >= VTH packets] (95% Clopper-Pearson), and the runs a
  fixed-sample estimate of P_T would need for a 95% interval of +-10% relative half-width;
- the per-round rate of such rounds (vBad / rounds per run) and the runs and simulated steps needed to estimate it to
  +-10% relative half-width (95%, normal approximation from the runs' variance);
- Wald's SPRT on "P_T >= THETA" (H+: P_T >= THETA + DELTA, H-: P_T <= THETA - DELTA, alpha = beta = ALPHA) on
  fresh runs.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fabric/horizon_sweep.py out.jsonl SIZE T1,T2,... [NAME=value ...]
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fabric_lib import build, compile_fabric, horizon, runs, state_vars  # noqa: E402
from src.netmdp.hyptest.hyptest import ErrTols, HypResult  # noqa: E402
from src.netmdp.hyptest.intervals import clopper_pearson  # noqa: E402
from src.netmdp.hyptest.wald_sprt import WaldSprt  # noqa: E402
from src.netmdp.sampler.sampler import Sampler  # noqa: E402

BASE = dict(B=16, NCAP=8, SLEN=4, WIN=10, PERIOD=60, THRESH=10, VTH=10, LV=0.3, LB=0.05)
THETA, DELTA, ALPHA, REL = 0.5, 0.05, 0.01, 0.10
MAX_RUNS = 20_000


class Truncated(Exception):
    pass


class BatchSampler(Sampler):
    def __init__(self, jm, T, seed, batch):
        super().__init__()
        self.jm, self.T, self.seed, self.batch = jm, T, seed, batch
        self.buf, self.pos, self.b, self.n = np.zeros(0), 0, 0, 0

    def sample(self):
        if self.n >= MAX_RUNS:
            raise Truncated
        if self.pos == len(self.buf):
            out, _ = runs(self.jm, self.batch, self.T, self.seed * 100000 + self.b)
            self.buf, self.pos, self.b = out["victim"], 0, self.b + 1
        x = int(self.buf[self.pos])
        self.pos, self.n = self.pos + 1, self.n + 1
        return x


def point(size, defs, budget):
    nl, h, ns = (int(x) for x in size.split("x"))
    d = dict(defs, NL=nl, H=h, NS=ns)
    with tempfile.TemporaryDirectory() as tmp:
        model, compile_s, _ = compile_fabric(d, Path(tmp) / "f.jani")
    T = horizon(model)
    jm, build_s = build(model)
    nv = state_vars(model)
    del model
    t = time.time()
    runs(jm, 5, T, seed=1)
    per_run = (time.time() - t) / 5
    n = int(min(50_000, max(100, budget / per_run)))
    t = time.time()
    est, steps = runs(jm, n, T, seed=2)
    sim_s = time.time() - t
    rounds = -(-T // int(d["PERIOD"]))
    k = int(est["victim"].sum())
    p = k / n
    lo, hi = clopper_pearson(k, n, 0.95)
    rate = est["vBad"] / rounds
    m, sd = float(rate.mean()), float(rate.std(ddof=1))
    n_rate = int(np.ceil((1.96 * sd / (REL * m)) ** 2)) if m > 0 else None
    n_p = int(np.ceil(1.96 ** 2 * (1 - p) / (REL ** 2 * p))) if 0 < p < 1 else None
    res = {"size": size, "T": T, "rounds": rounds, "defines": d, "state_vars": nv, "compile_s": round(compile_s, 2),
           "build_s": round(build_s, 2), "runs": n, "per_run_ms": round(1000 * sim_s / n, 3),
           "per_step_us": round(1e6 * sim_s / n / T, 2), "P_T": [p, lo, hi],
           "runs_for_P_T_10pct": n_p, "round_rate": [m, sd], "runs_for_rate_10pct": n_rate,
           "steps_for_rate_10pct": n_rate * T if n_rate else None,
           "seconds_for_rate_10pct": round(n_rate * sim_s / n, 1) if n_rate else None,
           "mean_vLost_per_round": round(float(est["vLost"].mean()) / rounds, 4),
           "mean_oLost_per_round": round(float(est["oLost"].mean()) / rounds, 2)}
    sampler = BatchSampler(jm, T, seed=3, batch=max(10, min(500, int(5 / per_run))))
    sprt = WaldSprt(THETA, ErrTols(ALPHA, ALPHA), DELTA, MAX_RUNS)
    t = time.time()
    try:
        r = sprt.run_test(sampler)
        dec = {HypResult.ACCEPT_H_PLUS: "H+", HypResult.ACCEPT_H_MINUS: "H-"}.get(r.get_result(), "inconclusive")
        sn = r.get_n()
    except Truncated:
        dec, sn = "inconclusive", sampler.n
    res["sprt"] = {"theta": THETA, "delta": DELTA, "alpha": ALPHA, "decision": dec, "runs": sn,
                   "simulated_runs": sampler.b * sampler.batch, "test_s": round(time.time() - t, 2)}
    return res


def main():
    if sys.argv[1] == "--point":
        print(json.dumps(point(sys.argv[2], json.loads(sys.argv[3]), float(sys.argv[4]))))
        return
    out_path, size, Ts = Path(sys.argv[1]), sys.argv[2], [int(x) for x in sys.argv[3].split(",")]
    defs = dict(BASE)
    for kv in sys.argv[4:]:
        k, v = kv.split("=")
        defs[k] = v
    budget = float(defs.pop("BUDGET", 120))
    done = set()
    if out_path.exists():
        done = {json.loads(l)["T"] for l in out_path.read_text().splitlines() if l.strip()}
    for T in Ts:
        if T in done:
            continue
        r = subprocess.run([sys.executable, __file__, "--point", size, json.dumps(dict(defs, T=T)), str(budget)],
                           capture_output=True, text=True, timeout=6 * 3600)
        res = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else \
            {"size": size, "T": T, "error": r.stderr.strip()[-2000:]}
        with out_path.open("a") as f:
            f.write(json.dumps(res) + "\n")
        if "error" in res:
            print(f"T={T}: FAILED {res['error'][-300:]}", flush=True)
            continue
        print(f"T={T} ({res['rounds']} rounds): {res['per_run_ms']} ms/run, {res['per_step_us']} us/step; "
              f"P_T {res['P_T'][0]:.4f} [{res['P_T'][1]:.4f}, {res['P_T'][2]:.4f}] ({res['runs']} runs); "
              f"round rate {res['round_rate'][0]:.4f}, runs for +-10%: {res['runs_for_rate_10pct']} "
              f"({res['steps_for_rate_10pct']} steps); SPRT {res['sprt']['decision']} after {res['sprt']['runs']}",
              flush=True)


if __name__ == "__main__":
    main()
