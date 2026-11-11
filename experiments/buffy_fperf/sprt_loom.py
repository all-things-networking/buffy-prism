"""
The pre-registered sequential tests of docs/notes/prereg-sprt-loom.md, run from prereg_sprt.json alone.

Per test, in the file's order:
- compile buffy/examples/jani/loom_isolation.buffy with the test's -D values and the file's flags;
- simulate runs in batches of `batch` (the batch with index b uses the seed `seed * 100000 + b`, a
  stream determined by the registered seed);
- feed the runs one by one, in order, to Wald's SPRT (src/netmdp/hyptest/wald_sprt.py), stopping at
  its first boundary crossing; runs left in the batch are discarded unseen;
- at `max_runs` runs without a decision, the test is inconclusive.

One JSON line per finished test goes to the output file. A test already in it is not run again, so an
interrupted run resumes with the same seeds and gives the same results.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_fperf/sprt_loom.py prereg_sprt.json results.jsonl [family]
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

from src.netmdp.hyptest.hyptest import ErrTols, HypResult
from src.netmdp.hyptest.wald_sprt import WaldSprt
from src.netmdp.sampler.sampler import Sampler
from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[2]
SHARE, W = 40, 20


class Truncated(Exception):
    pass


class BatchSampler(Sampler):
    """ Starved-window outcomes (0/1) of the model's runs, one at a time, simulated `batch` at a time. """

    def __init__(self, jm, horizon, seed, batch, max_runs):
        super().__init__()
        self.jm, self.horizon, self.seed, self.batch, self.max_runs = jm, horizon, seed, batch, max_runs
        self.buf, self.pos, self.b, self.n, self.k, self.sim_s = np.zeros(0), 0, 0, 0, 0, 0.0

    def sample(self):
        if self.n >= self.max_runs:
            raise Truncated
        if self.pos == len(self.buf):
            t = time.time()
            r = self.jm.simulate_rewards(self.batch, self.horizon, None, seed=self.seed * 100000 + self.b)
            self.sim_s += time.time() - t
            self.buf = ((r.final["waiting"] > 0.5) & (100 * r.final["w1"] <= SHARE * W)).astype(int)
            self.pos, self.b = 0, self.b + 1
        x = int(self.buf[self.pos])
        self.pos += 1
        self.n += 1
        self.k += x
        return x


def run_test(reg, t, d):
    defs = [x for k, v in t["defines"].items() for x in ("-D", f"{k}={v}")]
    out = Path(d) / f"t{t['index']}.jani"
    t0 = time.time()
    subprocess.run([str(ROOT / "buffy/build/buffyc-mc"), str(ROOT / reg["model"]), *reg["flags"], *defs, "-o", str(out)],
                   check=True, capture_output=True, timeout=3600)
    t1 = time.time()
    model = json.loads(out.read_text())
    horizon = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
    jm = JaniModel(model, observables={"w1": "loom_w1", "waiting": {"op": "ite", "if": "loom_waiting", "then": 1, "else": 0}})
    t2 = time.time()
    sampler = BatchSampler(jm, horizon, t["seed"], reg["batch"], t["max_runs"])
    sprt = WaldSprt(t["theta"], ErrTols(t["alpha"], t["beta"]), t["delta"], t["max_runs"])
    try:
        res = sprt.run_test(sampler)
        decision = {HypResult.ACCEPT_H_PLUS: "H+", HypResult.ACCEPT_H_MINUS: "H-"}.get(res.get_result(), "inconclusive")
        n, mean = res.get_n(), res.get_sample_mean()
    except Truncated:
        decision, n, mean = "inconclusive", sampler.n, sampler.k / max(sampler.n, 1)
    t3 = time.time()
    return {"index": t["index"], "family": t["family"], "defines": t["defines"], "decision": decision,
            "predicted": t["predict"], "runs": n, "sample_mean": mean, "max_runs": t["max_runs"],
            "compile_s": round(t1 - t0, 2), "build_s": round(t2 - t1, 2), "test_s": round(t3 - t2, 2),
            "simulate_s": round(sampler.sim_s, 2), "batches": sampler.b, "state_vars": len(model["variables"])}


def main():
    reg_path, out_path = Path(sys.argv[1]), Path(sys.argv[2])
    family = sys.argv[3] if len(sys.argv) > 3 else None
    reg = json.loads(reg_path.read_text())
    done = set()
    if out_path.exists():
        done = {json.loads(l)["index"] for l in out_path.read_text().splitlines() if l.strip()}
    with tempfile.TemporaryDirectory() as d:
        for t in reg["tests"]:
            if t["index"] in done or (family and t["family"] != family):
                continue
            r = run_test(reg, t, d)
            with out_path.open("a") as f:
                f.write(json.dumps(r) + "\n")
            print(f"[{r['family']} {r['index']:>2}] {r['defines']}: {r['decision']} (predicted {r['predicted']}) after "
                  f"{r['runs']} runs, mean {r['sample_mean']:.5f}; "
                  f"compile {r['compile_s']} s, build {r['build_s']} s, test {r['test_s']} s", flush=True)


if __name__ == "__main__":
    main()
