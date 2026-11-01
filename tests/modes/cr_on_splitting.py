"""
Chow-Robbins (anytime and fixed-width) on importance-splitting samples, compared with SPRT on base SMC, for the
STAT 535C Experiment 3 hypothesis (θ = 1.5e-4, ζ = 1e-4, α = β = 0.05; true p ≈ 4.09e-4).

modes exports the empirical distribution of per-run RESTART estimates (--cdf); the tests are run on i.i.d. draws
from it (a bootstrap of the RESTART run distribution), and sample counts are converted to time with the per-run
costs measured by run_course_experiments.py. Usage: PYTHONPATH=. python tests/modes/cr_on_splitting.py [runs]
"""
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from src.netmdp.hyptest.chow_robbins import ChowRobbins
from src.netmdp.hyptest.hyptest import ErrTols
from src.netmdp.hyptest.wald_sprt import WaldSprt
from tests.sequential_test_comparison import run_cr_anytime, run_cr_fixed, run_sprt

MODES = os.environ.get("MODES", "/Users/jkai/buffy-prism/Modest/modest")
HERE = Path(__file__).parent
THETA, ZETA = 0.00015, 0.0001


def restart_distribution(runs: int) -> tuple[np.ndarray, np.ndarray]:
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        out = f.name
    subprocess.run([MODES, "modes", str(HERE / "fqcodel_5i_weibull_dtmc_535c.jani"), "--props", "p_gt8", "--rare",
                    "Restart", "--levels", "ExpectedSuccess", "--ifun-prop", "imp", "0", "9", "-N", str(runs),
                    "-J", "4", "--seed", "21", "--cdf", out, "CSV", "-Y"], check=True, capture_output=True)
    with open(out) as f:
        rows = list(csv.reader(f))[1:]
    os.unlink(out)
    values = np.array([float(r[0]) for r in rows])
    cdf = np.array([float(r[2]) for r in rows])
    return values, np.diff(np.concatenate([[0.0], cdf]))


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 200_000
    values, probs = restart_distribution(runs)
    probs = probs / probs.sum()
    mean, var = float(values @ probs), float(((values - values @ probs) ** 2) @ probs)
    print(f"RESTART per-run distribution from {runs} runs: mean {mean:.4g}, sd/mean {np.sqrt(var) / mean:.1f}, "
          f"{len(values)} support points")
    replication = json.loads((HERE / "results" / "course_replication.json").read_text())["runs"]["3"]
    cost = {name: np.mean([r["time"] / r["runs"] for r in rows]) for name, rows in replication.items()}
    errs = ErrTols(0.05, 0.05)
    rng = np.random.default_rng(5)
    reps, horizon = 200, 400_000
    out = {}
    anytime, fixed = ChowRobbins(THETA, errs, ZETA, None), ChowRobbins(THETA, errs, ZETA, None, mode="fixed_width")
    for name, test, fn in [("CR anytime", anytime, run_cr_anytime), ("CR fixed-width", fixed, run_cr_fixed)]:
        res = [fn(test, rng.choice(values, size=horizon, p=probs)) for _ in range(reps)]
        out[f"RESTART + {name}"] = (res, cost["RESTART/CR"])
    sprt = WaldSprt(THETA, errs, ZETA, None)
    res = [run_sprt(sprt, (rng.random(horizon) < mean).astype(np.float64)) for _ in range(reps)]
    out["base + SPRT"] = (res, cost["base/CR"])
    for name, (res, c) in out.items():
        n = np.mean([k for k, _ in res])
        print(f"  {name:26s} P(H+)={np.mean([d == '+' for _, d in res]):.3f}  mean runs {n:9,.0f}  "
              f"≈ {n * c:6.2f} s at {c * 1e3:.3f} ms/run")


if __name__ == "__main__":
    main()
