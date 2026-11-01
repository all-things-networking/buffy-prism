"""
Replicates the STAT 535C FQ-CoDel experiments (slides "Experiments 1-3") with the Modest Toolset's modes:
base SMC with SPRT and Chow-Robbins, RESTART (fixed splitting) and weighted fixed effort with Chow-Robbins, both
with expected-success level selection and the course importance function iq5_deqs_bl.

Usage (after make_course_jani.py):
    PYTHONPATH=. python tests/modes/run_course_experiments.py [reps] [workers]
Writes tests/modes/results/course_replication.json and prints a summary table.
"""
import json
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

MODES = os.environ.get("MODES", "/Users/jkai/buffy-prism/Modest/modest")
HERE = Path(__file__).parent
JANI = HERE / "fqcodel_5i_weibull_dtmc_535c.jani"
OUT = HERE / "results" / "course_replication.json"

# Course experiments: k (goal iq5_deqs_bl > k), theta, zeta; alpha = beta = 0.05 throughout.
EXPERIMENTS = {1: (2, 0.70, 0.01), 2: (4, 0.011, 0.001), 3: (8, 0.00015, 0.0001)}


def configs(k: int, zeta: float) -> dict[str, list[str]]:
    # Course Chow-Robbins: stop when the half-width of the two-sided 1-2*alpha CI is below zeta/2 (alpha = beta).
    cr = ["--statistics", "ChowRobbins", "-W", str(zeta / 2), "-C", "0.90"]
    rare = ["--levels", "ExpectedSuccess", "--ifun-prop", "imp", "0", str(k + 1)]
    return {
        "base/SPRT": ["--props", f"h_gt{k}", "--statistics", "SPRT", "-W", str(zeta), "-C", "0.95"],
        "base/CR": ["--props", f"p_gt{k}"] + cr,
        "RESTART/CR": ["--props", f"p_gt{k}", "--rare", "Restart"] + rare + cr,
        "WFE(8)/CR": ["--props", f"p_gt{k}", "--rare", "WeightedFixedEffort", "--rare-effort", "8"] + rare + cr,
    }


def run_modes(args: list[str], seed: int) -> dict:
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        out = f.name
    cmd = [MODES, "modes", str(JANI), *args, "-J", "1", "--seed", str(seed), "-O", out, "Json", "-Y"]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    with open(out) as f:
        result = json.load(f)
    os.unlink(out)
    top = result["data"][0]
    prop = top["data"][0]
    values = {v["name"]: v["value"] for v in prop["values"]}
    groups = {g["group"]: {v["name"]: v["value"] for v in g["values"]} for g in prop.get("data", [])}
    decision = {"True": True, "False": False}.get(str(prop["value"]))  # SPRT reports its decision as a string
    if decision is not None:
        estimate = float(values["Estimated probability"])
    else:
        estimate = float(groups.get("Sample data", {}).get("Mean", prop["value"]))
    variance = groups.get("Sample data", {}).get("Variance")
    if variance is None:  # Bernoulli runs (SPRT reports no sample data)
        variance = estimate * (1 - estimate)
    time = {v["name"]: v["value"] for v in top["values"]}["Simulation time"]
    return {"seed": seed, "decision": decision,
            "estimate": estimate, "variance": float(variance), "runs": int(values["Runs used"]), "time": float(time),
            "levels": groups.get("Importance function", {}).get("Levels")}


def summarize(rows: list[dict], zeta: float) -> dict:
    n = np.mean([r["runs"] for r in rows])
    t = np.mean([r["time"] for r in rows])
    p = np.mean([r["estimate"] for r in rows])
    rel_sd = np.mean([np.sqrt(r["variance"]) / r["estimate"] for r in rows if r["estimate"] > 0])
    # Work-normalised relative variance of the final estimator, Var(p_hat_N)/p^2 * time = (sigma^2/p^2)(time/N).
    wnrv = np.mean([r["variance"] / r["estimate"] ** 2 * r["time"] / r["runs"] for r in rows if r["estimate"] > 0])
    decisions = [r["decision"] for r in rows if r["decision"] is not None]
    # modes' ChowRobbins is the original rule n >= (z/eps)^2 (s_n^2 + 1/n); the course ChowRobbins class omits the 1/n
    # regulariser, which dominates for rare events. Runs (and time at the measured cost per run) the course rule needs:
    z2_eps2 = 1.6448536269514722 ** 2 / (zeta / 2) ** 2
    n_course_cr = np.mean([z2_eps2 * r["variance"] for r in rows])
    t_course_cr = n_course_cr * np.mean([r["time"] / r["runs"] for r in rows])
    return {"N": n, "time_s": t, "estimate": p, "R_err": rel_sd, "a_N_course": rel_sd ** 2 * n,
            "a_t_course": rel_sd ** 2 * t, "wnrv": wnrv,
            "accept_H+": float(np.mean(decisions)) if decisions else None,
            "N_course_CR": n_course_cr, "time_course_CR_s": t_course_cr}


def main():
    reps = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else max(1, (os.cpu_count() or 2) - 2)
    jobs = [(e, name, args, seed) for e, (k, theta, zeta) in EXPERIMENTS.items()
            for name, args in configs(k, zeta).items() for seed in range(1, reps + 1)]
    with ThreadPoolExecutor(workers) as pool:
        outcomes = list(pool.map(lambda j: (j[0], j[1], run_modes(j[2], j[3])), jobs))
    results = {}
    for e, name, row in outcomes:
        results.setdefault(str(e), {}).setdefault(name, []).append(row)
    summary = {e: {name: summarize(rows, EXPERIMENTS[int(e)][2]) for name, rows in by.items()}
               for e, by in results.items()}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"experiments": EXPERIMENTS, "reps": reps, "runs": results, "summary": summary},
                              indent=1))
    for e, by in summary.items():
        k, theta, zeta = EXPERIMENTS[int(e)]
        print(f"\nExperiment {e}: P(deqs>{k} within 154 steps) vs theta={theta}, zeta={zeta}")
        print(f"  {'method':12s} {'N':>9s} {'time(s)':>8s} {'p_hat':>10s} {'R_err':>7s} {'a_N':>10s} {'a_t':>9s} "
              f"{'WNRV':>9s} {'H+':>5s} {'N(courseCR)':>11s} {'t(courseCR)':>11s}")
        for name, s in by.items():
            hp = "" if s["accept_H+"] is None else f"{s['accept_H+']:.2f}"
            print(f"  {name:12s} {s['N']:9.0f} {s['time_s']:8.2f} {s['estimate']:10.3g} {s['R_err']:7.2f} "
                  f"{s['a_N_course']:10.4g} {s['a_t_course']:9.3g} {s['wnrv']:9.2e} {hp:>5s} "
                  f"{s['N_course_CR']:11.0f} {s['time_course_CR_s']:11.2f}")


if __name__ == "__main__":
    main()
