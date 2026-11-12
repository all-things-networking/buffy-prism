"""
Axis 1 of the fabric scaling study: fabric size. For each size (NL leaves x H hosts per leaf x NS spines), in its own
process (so that one size's memory is freed before the next, on an 8 GB machine), one after the other:
- compile fabric.buffy to the native target (wall time and peak memory of buffyc-mc, from /usr/bin/time -l);
- build the simulator (clang);
- estimate P[loss], P[victim] (95% Clopper-Pearson) and the counters' means from `runs` runs (fewer if that would
  take longer than `budget` seconds), and the per-run and per-host-step cost;
- run Wald's SPRT on the claim "the victim (the aggregator's rack neighbour) loses a packet in more than THETA of the
  query rounds": H+: P >= THETA + DELTA against H-: P <= THETA - DELTA, alpha = beta = ALPHA, on fresh runs, and
  compare its run count with the fixed-sample test of the same alpha, beta, delta (normal approximation).
One JSON line per size goes to the output file; sizes already in it are skipped.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fabric/size_sweep.py out.jsonl SIZES [NAME=value ...]
  SIZES: comma-separated NLxHxNS, e.g. 4x8x2,8x8x2
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).parent))
from fabric_lib import BUFFYC, COUNTERS, MODEL, build, horizon, runs, state_vars  # noqa: E402
from src.netmdp.hyptest.hyptest import ErrTols, HypResult  # noqa: E402
from src.netmdp.hyptest.intervals import clopper_pearson  # noqa: E402
from src.netmdp.hyptest.wald_sprt import WaldSprt  # noqa: E402
from src.netmdp.sampler.sampler import Sampler  # noqa: E402

BASE = dict(B=16, NCAP=8, SLEN=4, WIN=10, T=60, THRESH=10, VTH=1, LV=0.3, LB=0.05)
THETA, DELTA, ALPHA = 0.10, 0.02, 0.01
MAX_RUNS, BATCH = 200_000, 200


class Truncated(Exception):
    pass


class BatchSampler(Sampler):
    """ The victim's 0/1 outcomes of fresh runs, simulated BATCH at a time (batch b uses seed `seed * 100000 + b`). """

    def __init__(self, jm, T, seed):
        super().__init__()
        self.jm, self.T, self.seed = jm, T, seed
        self.buf, self.pos, self.b, self.n, self.sim_s = np.zeros(0), 0, 0, 0, 0.0

    def sample(self):
        if self.n >= MAX_RUNS:
            raise Truncated
        if self.pos == len(self.buf):
            t = time.time()
            out, _ = runs(self.jm, BATCH, self.T, self.seed * 100000 + self.b)
            self.sim_s += time.time() - t
            self.buf, self.pos, self.b = out["victim"], 0, self.b + 1
        x = int(self.buf[self.pos])
        self.pos, self.n = self.pos + 1, self.n + 1
        return x


def fixed_sample_n(theta, delta, alpha, beta):
    p0, p1 = theta - delta, theta + delta
    z = norm.ppf(1 - alpha) * np.sqrt(p0 * (1 - p0)) + norm.ppf(1 - beta) * np.sqrt(p1 * (1 - p1))
    return int(np.ceil((z / (p1 - p0)) ** 2))


def point(size: str, defs: dict, n_runs: int, budget: float) -> dict:
    nl, h, ns = (int(x) for x in size.split("x"))
    d = dict(defs, NL=nl, H=h, NS=ns)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "fabric.jani"
        dflags = [x for k, v in d.items() for x in ("-D", f"{k}={v}")]
        t0 = time.time()
        r = subprocess.run(["/usr/bin/time", "-l", str(BUFFYC), str(MODEL), "--target", "native", *dflags,
                            "-o", str(out)], capture_output=True, text=True, timeout=3600)
        compile_s = time.time() - t0
        if r.returncode != 0:
            return {"size": size, "defines": d, "error": r.stderr.strip()[-2000:]}
        rss = int(re.search(r"(\d+)\s+maximum resident set size", r.stderr).group(1)) / 1e6
        jani_mb = out.stat().st_size / 1e6
        model = json.loads(out.read_text())
    T = horizon(model)
    jm, build_s = build(model)
    c_mb = len(model["x-buffy-native"]["c"]) / 1e6
    nv = state_vars(model)
    del model
    # estimation
    t = time.time()
    probe, _ = runs(jm, 20, T, seed=1)
    per_run = (time.time() - t) / 20
    n = int(min(n_runs, max(200, budget / per_run)))
    t = time.time()
    est, steps = runs(jm, n, T, seed=2)
    sim_s = time.time() - t
    res = {"size": size, "hosts": nl * h, "fan_in": (nl - 1) * h - 1, "defines": d, "state_vars": nv,
           "compile_s": round(compile_s, 2), "compile_rss_mb": round(rss), "jani_mb": round(jani_mb, 1),
           "c_mb": round(c_mb, 1), "build_s": round(build_s, 2), "runs": n, "per_run_ms": round(1000 * sim_s / n, 3),
           "per_host_step_ns": round(1e9 * sim_s / n / T / (nl * h), 1)}
    for q in ("loss", "victim"):
        k = int(est[q].sum())
        lo, hi = clopper_pearson(k, n, 0.95)
        res[q] = [k / n, lo, hi]
    for c in COUNTERS:
        res[c] = round(float(est[c].mean()), 4)
    res["incast_lost_frac"] = round(res["oLost"] / (res["fan_in"] * int(d["SLEN"])), 4)
    # sequential test on fresh runs
    sampler = BatchSampler(jm, T, seed=3)
    sprt = WaldSprt(THETA, ErrTols(ALPHA, ALPHA), DELTA, MAX_RUNS)
    t = time.time()
    try:
        r = sprt.run_test(sampler)
        dec = {HypResult.ACCEPT_H_PLUS: "H+", HypResult.ACCEPT_H_MINUS: "H-"}.get(r.get_result(), "inconclusive")
        sn = r.get_n()
    except Truncated:
        dec, sn = "inconclusive", sampler.n
    res["sprt"] = {"theta": THETA, "delta": DELTA, "alpha": ALPHA, "decision": dec, "runs": sn,
                   "fixed_sample_runs": fixed_sample_n(THETA, DELTA, ALPHA, ALPHA), "test_s": round(time.time() - t, 2)}
    return res


def main():
    if sys.argv[1] == "--point":
        size, defs, n_runs, budget = sys.argv[2], json.loads(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])
        print(json.dumps(point(size, defs, n_runs, budget)))
        return
    out_path, sizes = Path(sys.argv[1]), sys.argv[2].split(",")
    defs = dict(BASE)
    for kv in sys.argv[3:]:
        k, v = kv.split("=")
        defs[k] = v
    n_runs, budget = int(defs.pop("RUNS", 10000)), float(defs.pop("BUDGET", 120))
    done = set()
    if out_path.exists():
        done = {json.loads(l)["size"] for l in out_path.read_text().splitlines() if l.strip()}
    for size in sizes:
        if size in done:
            continue
        r = subprocess.run([sys.executable, __file__, "--point", size, json.dumps(defs), str(n_runs), str(budget)],
                           capture_output=True, text=True, timeout=4 * 3600)
        if r.returncode != 0:
            res = {"size": size, "defines": defs, "error": r.stderr.strip()[-2000:]}
        else:
            res = json.loads(r.stdout.strip().splitlines()[-1])
        with out_path.open("a") as f:
            f.write(json.dumps(res) + "\n")
        if "error" in res:
            print(f"{size}: FAILED {res['error'][-300:]}", flush=True)
            continue
        print(f"{size}: {res['state_vars']} vars, compile {res['compile_s']} s / {res['compile_rss_mb']} MB, build "
              f"{res['build_s']} s, {res['per_run_ms']} ms/run ({res['per_host_step_ns']} ns/host-step); "
              f"P[victim] {res['victim'][0]:.4f} [{res['victim'][1]:.4f}, {res['victim'][2]:.4f}], incast lost "
              f"{res['incast_lost_frac']:.3f}; SPRT {res['sprt']['decision']} after {res['sprt']['runs']} runs", flush=True)


if __name__ == "__main__":
    main()
