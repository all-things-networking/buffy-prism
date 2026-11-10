# FPerf's contention points in Buffy

The Buffy programs are in `buffy/examples/fperf/`, and the equivalence harness is
`buffy/test/fperf/fperf_equiv_test.cpp` (part of `make test-fperf`). The design, results and
findings are in `docs/notes/fperf-cps-in-buffy.md`.

- `results/test_fperf.log`: `make test-fperf` at the default horizons.
- `results/equiv_*.log`: longer horizons. 2LRR is pinned-equivalent at T=6, Loom at T=3, and the
  leaf-spine is equivalent and refining at T=3.
- `run_ecmp.sh`: the probabilistic leaf-spine (ECMP collisions) on the native simulator.
  `results/ecmp_native.log` holds 100,000 runs per configuration.
