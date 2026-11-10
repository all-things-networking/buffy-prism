# FPerf's contention points in Buffy

The Buffy programs are in `buffy/examples/fperf/`, and the equivalence harness is
`buffy/test/fperf/fperf_equiv_test.cpp` (part of `make test-fperf`). The design, results and
findings are in `docs/notes/fperf-cps-in-buffy.md`.

- `results/test_fperf.log`: `make test-fperf` at the default horizons.
- `results/equiv_*.log`: longer horizons. 2LRR is pinned-equivalent at T=6, Loom at T=3, and the
  leaf-spine is equivalent and refining at T=3.
- `results/equiv_lsany3.log`: the any-stable-matching crossbar (`XBAR = 1`) is FPerf's relation,
  both directions, at T=3.
- `native_eval.py`: every bounded probability and C/I expected value of a Buffy JANI file, from the
  native simulator.
- `run_ecmp.sh`, `run_ecmp_load.sh`: the probabilistic leaf-spine (ECMP collisions; throughput
  against load). `results/ecmp_native.log` and `ecmp_load.log` hold them.
- `run_xbar.sh`: input- against output-proposing crossbar (`results/xbar.log`).
- `run_loom.sh`: Loom's tenant isolation against loads (`results/loom_load.log`).
- Priority starvation against load is exact (Storm on `buffy/examples/jani/prio_load.buffy`); its
  table is in the notes.
