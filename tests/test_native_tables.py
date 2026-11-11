"""
Lookup tables in the native simulator (jani_native._Translator._table) must not change the model: on
Buffy models whose expressions contain large selection trees (--condition-on's reweighted probabilities and
its tracker, factored LTL monitors), the builds with and without tables must give, in every state visited
by random walks, the same enabled edges and the same successors with the same probabilities, exactly.

Run from the repository root: PYTHONPATH=. python tests/test_native_tables.py
"""
import json
import os
import subprocess
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUFFYC = ROOT / "buffy" / "build" / "buffyc-mc"


def build(jani: dict, tables: bool):
    from src.netmdp.sim import jani_native
    old = os.environ.get("JM_NO_TABLES")
    os.environ["JM_NO_TABLES"] = "0" if tables else "1"
    try:
        m = jani_native.JaniModel(jani)
    finally:
        if old is None:
            os.environ.pop("JM_NO_TABLES")
        else:
            os.environ["JM_NO_TABLES"] = old
    src = "\n".join(t for t in m._tr.tables)
    return m, src


def compare(jani: dict, walks: int, label: str):
    a, ta = build(jani, True)
    b, tb = build(jani, False)
    assert ta and not tb, f"{label}: expected lookup tables with tables on and none with them off"
    rng = np.random.default_rng(1)
    states = 0
    for _ in range(walks):
        s = a.initial_state()
        for _ in range(400):
            ea, eb = a.enabled_edges(s), b.enabled_edges(s)
            assert np.array_equal(ea, eb), f"{label}: enabled edges differ"
            if len(ea) == 0:
                break
            e = int(ea[rng.integers(len(ea))])
            sa, sb = a.successors(s, e), b.successors(s, e)
            assert len(sa) == len(sb), f"{label}: successor counts differ"
            for (pa, xa), (pb, xb) in zip(sa, sb):
                assert pa == pb and np.array_equal(xa, xb), f"{label}: successor differs ({pa} vs {pb})"
            states += 1
            a.step(s, e, rng.random())
    print(f"{label}: {len(ta.splitlines())} tables; {states} states compared, identical")


def outcast_with_condition(d: str) -> str:
    """ outcast.buffy with learned condition c4 as a `given` query: three factored monitors (162-621 states). """
    cond = json.loads((ROOT / "experiments/buffy_outcast/results/conds_oc_NA2.json").read_text())["conditions"][4]
    lines = (ROOT / "buffy/examples/jani/outcast.buffy").read_text().splitlines()
    prog = "\n".join(l for l in lines if not l.startswith(("query", "reward")))
    prog += f"\nquery c4: P=? [ F<=T (time == T && outcast.got[NA] <= 13) ] given {cond['buffy']};\n"
    path = Path(d) / "outcast_c4.buffy"
    path.write_text(prog)
    return str(path)


def main():
    with tempfile.TemporaryDirectory() as d:
        for name, args in (("cond_input --condition-on both",
                            [str(ROOT / "buffy/examples/jani/cond_input.buffy"), "--condition-on", "both"]),
                           ("outcast, a learned condition (factored monitors)",
                            [outcast_with_condition(d), "-D", "NA=2", "--stop-at-horizon"]),
                           ("fq_conditions --condition-on se",
                            [str(ROOT / "experiments/buffy_conditioning/fq_conditions.buffy"), "--condition-on", "se"])):
            out = Path(d) / "m.jani"
            subprocess.run([str(BUFFYC), *args, "-o", str(out)], check=True, capture_output=True)
            compare(json.loads(out.read_text()), 40, name)


if __name__ == "__main__":
    main()
