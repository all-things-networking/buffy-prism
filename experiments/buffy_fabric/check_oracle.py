"""
Compare the native simulator on fabric.buffy (buffyc-mc --target native) with the independent oracle
fabric_oracle.py at small sizes: P[loss], P[victim] (two-proportion z) and the mean of every cumulative
counter at T (Welch z). With the 12 configurations x 9 quantities, a |z| above 3.55 is suspicious
(Bonferroni at 0.05 over 108 comparisons, two-sided).

Usage (from the repository root): PYTHONPATH=. python experiments/buffy_fabric/check_oracle.py [runs]
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from fabric_lib import COUNTERS, build, compile_fabric, horizon, runs  # noqa: E402

HERE = Path(__file__).parent
CONFIGS = [
    {},
    {"ECMP": 1},
    {"NL": 2, "H": 3, "NS": 1, "B": 3},
    {"NL": 4, "H": 2, "NS": 3, "LB": 0.2},
    {"NL": 3, "H": 3, "NS": 2, "SLEN": 4, "WIN": 2, "THRESH": 4, "VTH": 2},
    {"NL": 3, "H": 2, "NS": 2, "PERIOD": 10, "T": 45, "THRESH": 3},
    {"NL": 2, "H": 4, "NS": 2, "ECMP": 1, "NCAP": 2, "LV": 0.6, "LB": 0.1},
    {"NL": 5, "H": 2, "NS": 2, "PERIOD": 15, "T": 40, "B": 2, "ECMP": 1},
    # many draws per step (these exposed the simulator's precision bug, see tests/test_native_precision.py)
    {"NL": 8, "H": 8, "NS": 4, "B": 8, "NCAP": 8, "SLEN": 4, "WIN": 10, "T": 60, "THRESH": 10},
    {"NL": 8, "H": 4, "NS": 4, "T": 60, "THRESH": 10, "VTH": 2, "LB": 0.1},
    {"NL": 6, "H": 6, "NS": 3, "B": 6, "PERIOD": 20, "T": 60, "THRESH": 20, "ECMP": 1},
    {"NL": 4, "H": 16, "NS": 8, "B": 4, "SLEN": 2, "WIN": 6, "T": 40, "THRESH": 8, "LV": 0.5},
]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    worst = 0.0
    with tempfile.TemporaryDirectory() as d:
        for i, cfg in enumerate(CONFIGS):
            model, _, _ = compile_fabric(cfg, Path(d) / f"c{i}.jani")
            jm, _ = build(model)
            nat, _ = runs(jm, n, horizon(model), seed=1000 + i)
            o = subprocess.run([sys.executable, str(HERE / "fabric_oracle.py"), str(n), str(77 + i),
                                *[f"{k}={v}" for k, v in cfg.items()]], capture_output=True, text=True, check=True)
            ora = eval(o.stdout.strip())
            line = []
            for q in ("loss", "victim"):
                a, b = float(nat[q].mean()), ora[q]
                p = (a + b) / 2
                z = (a - b) / max(np.sqrt(2 * p * (1 - p) / n), 1e-12)
                worst = max(worst, abs(z))
                line.append(f"{q} {a:.4f}/{b:.4f} (z {z:+.1f})")
            for c in COUNTERS:
                a, b = float(nat[c].mean()), ora[c]
                se = np.sqrt((nat[c].var(ddof=1) + ora[c + "_sd"] ** 2) / n)
                z = (a - b) / se if se > 0 else (0.0 if a == b else np.inf)
                worst = max(worst, abs(z))
                line.append(f"{c} {a:.3f}/{b:.3f} (z {z:+.1f})")
            print(f"[{i}] {cfg or 'defaults'}: {len(model['variables'])} vars\n    " + "\n    ".join(line), flush=True)
    print(f"largest |z| = {worst:.2f} over {len(CONFIGS) * (2 + len(COUNTERS))} comparisons "
          f"({'consistent' if worst < 3.55 else 'SUSPICIOUS'}; native/oracle, {n} runs each)")


if __name__ == "__main__":
    main()
