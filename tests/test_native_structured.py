"""
Buffy's structured native step (`buffyc-mc --target native`: C that follows the program's structure) must
compute exactly what the unrolled step computes (`--native-dag`: one C temporary per DAG node). For every
example, and for variants that exercise the other code paths (--stop-at-horizon, --prune-violations,
--fifo-buffers, --saturate, --condition-on over one and over several sources, factored monitors), random
walks visit states in which both cores must give the same enabled edges and, for every destination, the
same successor, probability and rewards. Where a step has too many destinations to enumerate, both take
the same sampled destination instead.

Run from the repository root: PYTHONPATH=. python tests/test_native_structured.py [name-filter]
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

from src.netmdp.sim.jani_native import JaniModel

ROOT = Path(__file__).resolve().parents[1]
BUFFYC = ROOT / "buffy" / "build" / "buffyc-mc"
EX = ROOT / "buffy" / "examples" / "jani"

VARIANTS = {
    "deck_rr": [["--prune-violations"]],
    "classes_fifo": [["--fifo-buffers"]],
    "classes_tandem": [["--fifo-buffers"]],
    "arith": [["--saturate"]],
    "bursty": [["--saturate"]],
    "cond_input": [["--condition-on", "both"], ["--condition-on", "early", "--stop-at-horizon"]],
    "cond_joint": [["--condition-on", "mixed"], ["--condition-on", "heavy"]],
    "pfc": [["--stop-at-horizon"]],
    "outcast": [["--stop-at-horizon", "--factor-monitors"]],
    "loom_isolation": [["--stop-at-horizon", "-D", "NC=2", "-D", "CAP=4"]],
}


def compile_pair(src, flags, d):
    outs = []
    for extra in ([], ["--native-dag"]):
        out = Path(d) / f"m{len(outs)}.jani"
        r = subprocess.run([str(BUFFYC), str(src), "--target", "native", *flags, *extra, "-o", str(out)],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            return None, r.stderr.strip()
        if not extra and "does not support" in r.stderr:
            return None, "structured step unsupported: " + r.stderr.strip()
        outs.append(json.loads(out.read_text()))
    return outs, None


def compare(ja, jb, label, walks=12, steps=80, enum_max=2000):
    a, b = JaniModel(ja), JaniModel(jb)
    assert "bf_sstep" in ja["x-buffy-native"]["c"] and "bf_sstep" not in jb["x-buffy-native"]["c"], label
    rng = np.random.default_rng(7)
    states = dests = 0
    for _ in range(walks):
        s = a.initial_state()
        assert np.array_equal(s, b.initial_state()), f"{label}: initial states differ"
        for _ in range(steps):
            ea, eb = a.enabled_edges(s), b.enabled_edges(s)
            assert np.array_equal(ea, eb), f"{label}: enabled edges differ"
            if len(ea) == 0:
                break
            e = int(ea[rng.integers(len(ea))])
            if 0 < a.lib.jm_ndest(e) <= enum_max:
                sa, sb = a.successors(s, e, rewards=True), b.successors(s, e, rewards=True)
                assert len(sa) == len(sb), f"{label}: successor counts differ"
                for (pa, xa, ra), (pb, xb, rb) in zip(sa, sb):
                    assert pa == pb, f"{label}: probabilities differ ({pa} vs {pb})"
                    assert np.array_equal(xa, xb), f"{label}: successors differ:\n{xa}\n{xb}"
                    assert np.array_equal(ra, rb), f"{label}: rewards differ ({ra} vs {rb})"
                dests += len(sa)
            u = rng.random()
            sa, sb = s.copy(), s.copy()
            da, db = a.step(sa, e, u), b.step(sb, e, u)
            assert da == db and np.array_equal(sa, sb), f"{label}: sampled step differs"
            s = sa
            states += 1
    return states, dests


def main():
    filt = sys.argv[1] if len(sys.argv) > 1 else ""
    cases = []
    for f in sorted(EX.glob("*.buffy")):
        cases.append((f.stem, f, []))
        for v in VARIANTS.get(f.stem, []):
            cases.append((f.stem + " " + " ".join(v), f, v))
    fails = 0
    with tempfile.TemporaryDirectory() as d:
        for label, src, flags in cases:
            if filt not in label:
                continue
            pair, msg = compile_pair(src, flags, d)
            if pair is None:
                if "joint traffic choices" in (msg or "") or "query" in (msg or "") and "horizon" in (msg or ""):
                    print(f"skip {label}: {msg.splitlines()[-1]}")
                    continue
                print(f"FAIL {label}: {msg}")
                fails += 1
                continue
            try:
                n, k = compare(*pair, label)
                print(f"ok   {label}: {n} states, {k} destinations identical; C {len(pair[0]['x-buffy-native']['c']) // 1000} kB "
                      f"structured, {len(pair[1]['x-buffy-native']['c']) // 1000} kB unrolled")
            except AssertionError as e:
                print(f"FAIL {label}: {e}")
                fails += 1
    print("all identical" if not fails else f"{fails} failures")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
