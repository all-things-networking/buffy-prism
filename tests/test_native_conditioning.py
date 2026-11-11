"""
On-demand conditioning (`buffyc-mc --target native --condition-on q`): the simulator computes h lazily. On
buffy/examples/jani/cond_input.buffy, whose conditional probabilities are known exactly (Storm's _joint /
_given, as in buffy's test/jani), P(condition) must equal the exact value to rounding, and P(formula |
condition) from 1,000,000 conditioned runs must lie in its 99.9% Clopper-Pearson interval.

Run from the repository root: PYTHONPATH=. python tests/test_native_conditioning.py
"""
import json
import subprocess
import tempfile
from pathlib import Path

from src.netmdp.hyptest.intervals import clopper_pearson
from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[1]
BUFFYC = ROOT / "buffy" / "build" / "buffyc-mc"
# query: (P(condition), P(formula | condition)), exact (Storm, buffy test/jani)
EXACT = {"early": (0.49, 0.2642984693877551), "quiet": (0.43264, 0.257850637943787),
         "both": (0.228928, 0.027185403270897402)}


def main():
    with tempfile.TemporaryDirectory() as d:
        for q, (pc, pq) in EXACT.items():
            out = Path(d) / f"{q}.jani"
            subprocess.run([str(BUFFYC), str(ROOT / "buffy/examples/jani/cond_input.buffy"), "--target", "native",
                            "--condition-on", q, "-o", str(out)], check=True, capture_output=True)
            j = json.loads(out.read_text())
            e = next(p for p in j["properties"] if p["name"] == q)["expression"]["values"]["exp"]["right"]
            m = JaniModel(j, observables={"g": {"op": "ite", "if": e, "then": 1, "else": 0}})
            got = m.condition_probability()
            assert abs(got - pc) < 1e-12, f"{q}: P(condition) {got!r}, exact {pc}"
            n = 1_000_000
            r = m.simulate_rewards(n, 6, None, seed=3)
            k = int(((r.state_cumulative["g"] > 0) | (r.final["g"] > 0)).sum())
            lo, hi = clopper_pearson(k, n, 0.999)
            assert lo <= pq <= hi, f"{q}: P(formula | condition) {k / n} [{lo}, {hi}], exact {pq}"
            print(f"{q}: P(condition) = {got:.12g} (exact {pc}); P(formula | condition) = {k / n:.5f} "
                  f"[{lo:.5f}, {hi:.5f}] (exact {pq:.5f}); h for {m.condition_states()} input states")


if __name__ == "__main__":
    main()
