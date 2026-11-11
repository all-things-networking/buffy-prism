"""
Lookup tables in the native simulator (jani_native._Translator): for a compiled model, build it with and
without tables (fresh compile caches), and report the generated C size, the time to build (translate +
clang), and the hits of every reachability property in identical seeded runs, which must be equal.

Usage (from the repository root):
  PYTHONPATH=. python experiments/buffy_conditioning/compare_tables.py model.jani runs seed
"""
import json
import os
import subprocess
import sys
import tempfile
import time

CHILD = r"""
import json, os, sys, time
from pathlib import Path
t0 = time.time()
from src.netmdp.sim.jani_native import JaniModel, CACHE
model = json.loads(Path(sys.argv[1]).read_text())
T = next(int(v["type"]["upper-bound"]) for v in model["variables"] if v["name"] == "time")
obs = {}
for p in model["properties"]:
    e = p["expression"]["values"]["exp"]
    if e.get("op") == "U":
        obs[p["name"]] = {"op": "ite", "if": e["right"], "then": 1, "else": 0}
jm = JaniModel(model, observables=obs)
build = time.time() - t0
csize = sum(f.stat().st_size for f in CACHE.glob("*.c"))
r = jm.simulate_rewards(int(sys.argv[2]), T, None, seed=int(sys.argv[3]))
hits = {k: int(((r.state_cumulative[k] > 0) | (r.final[k] > 0)).sum()) for k in obs}
print(json.dumps({"build_s": build, "c_bytes": csize, "hits": hits}))
"""


def run(path, runs, seed, tables):
    with tempfile.TemporaryDirectory() as cache:
        env = dict(os.environ, NETMDP_JANI_CACHE=cache, JM_NO_TABLES="0" if tables else "1")
        out = subprocess.run([sys.executable, "-c", CHILD, path, str(runs), str(seed)], env=env,
                             capture_output=True, text=True, check=True, timeout=7200).stdout
        return json.loads(out.strip().splitlines()[-1])


def main():
    path, runs, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    on = run(path, runs, seed, True)
    off = run(path, runs, seed, False)
    same = on["hits"] == off["hits"]
    print(f"{path.split('/')[-1]}: tables {on['c_bytes'] / 1e6:.2f} MB C, built in {on['build_s']:.1f} s | "
          f"without {off['c_bytes'] / 1e6:.2f} MB, {off['build_s']:.1f} s | results identical: {same}")
    if not same:
        print("  with:", on["hits"], "\n  without:", off["hits"])


if __name__ == "__main__":
    main()
