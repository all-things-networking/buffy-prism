"""
Shared helpers for the leaf-spine fabric study: compile buffy/examples/jani/fabric.buffy with -D values to the
native target, build the simulator, and read the bad events and counters from batches of runs.
"""
import json
import resource
import subprocess
import time
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[2]
BUFFYC = ROOT / "buffy" / "build" / "buffyc-mc"
MODEL = ROOT / "buffy" / "examples" / "jani" / "fabric.buffy"
COUNTERS = ["oLost", "oGot", "vLost", "vGot", "bLost", "oBad", "vBad"]


def compile_fabric(defs: dict, out: Path, flags=(), timeout=3600):
    """ Compile with -D defs; returns (model dict, compile seconds, peak RSS of the compiler in MB). """
    d = [x for k, v in defs.items() for x in ("-D", f"{k}={v}")]
    t0 = time.time()
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    r = subprocess.run([str(BUFFYC), str(MODEL), "--target", "native", *flags, *d, "-o", str(out)],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    dt = time.time() - t0
    rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    model = json.loads(out.read_text())
    # ru_maxrss of children is the max over all children so far (bytes on macOS)
    return model, dt, max(rss, before) / 1e6


def horizon(model: dict) -> int:
    return next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")


def query_pred(model: dict, name: str):
    p = next(p for p in model["properties"] if p["name"] == name)
    return p["expression"]["values"]["exp"]["right"]


def build(model: dict, importance: dict | None = None, goals: dict | None = None):
    obs = {q: {"op": "ite", "if": query_pred(model, q), "then": 1, "else": 0} for q in ("loss", "victim")}
    obs.update({c: f"fabric_{c}" for c in COUNTERS})
    t0 = time.time()
    jm = JaniModel(model, observables=obs, importance=importance, goals=goals)
    return jm, time.time() - t0


def runs(jm: JaniModel, n: int, T: int, seed: int):
    """ n runs of T steps: per-run 0/1 outcomes of loss and victim, and the counters at time T. """
    r = jm.simulate_rewards(n, T, None, seed=seed)
    out = {q: ((r.state_cumulative[q] > 0) | (r.final[q] > 0)).astype(np.int8) for q in ("loss", "victim")}
    out.update({c: r.final[c] for c in COUNTERS})
    return out, r.steps


def state_vars(model: dict) -> int:
    return len(model["variables"])
