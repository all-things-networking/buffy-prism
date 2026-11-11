# Results: sequential certification of Loom tenant isolation at scale

*Pre-registration: `docs/notes/prereg-sprt-loom.md` and `experiments/buffy_fperf/prereg_sprt.json`
(buffy-prism `dbe0fa2`, Buffy `5ed2f76`), pushed before any run. Runner:
`experiments/buffy_fperf/sprt_loom.py`. Results: `results/sprt_loom.jsonl` (one line per test) and
`results/sprt_loom.log`.*

**Outcome.** All 36 tests decided, each as predicted, with no deviations from the registration. The
whole study took 57 minutes on one core of an 8 GB laptop, including compiling and building 36 models
of 25,000–200,000 state variables.

## Family A: MQPrio's isolation failure persists at scale

H+: P[starved] ≥ 0.31 against H−: P ≤ 0.29, with α = β = 0.0125 per test. Queue capacity 64, at the
box corner ρ = (0.6, 0.6, 0.1).

| cores | state variables | decision | runs | fixed-sample design | per run |
|---|---|---|---|---|---|
| 64 | 25,291 | **H+** | 427 | 10,597 | 4.9 ms |
| 128 | 50,315 | **H+** | 487 | 10,597 | 6.8 ms |
| 256 | 100,363 | **H+** | 637 | 10,597 | 13.8 ms |
| 512 | 200,459 | **H+** | 546 | 10,597 | 28.7 ms |

- **Runs and time.** SPRT needed 2,097 runs in all, against 42,388 for the fixed-sample design (20×):
  30 s of simulation instead of an estimated 9.6 minutes. Compiling and building the four models took
  42 s.
- **The claim.** In every one of these NIC configurations, from 64 to 512 cores, MQPrio starves
  tenant 1 in more than 29% of 20-step windows at a mild memcached share, at family-wise error 0.05.
- **Fractions in passing.** The fractions of starved windows seen when each test stopped were 0.41,
  0.39, 0.37 and 0.38, in line with the capacity-32 runs from 4 to 256 cores. They are not estimates:
  a sequential test's stopping rule biases them, and they come with no interval.

## Family B: the hierarchical policy across a grid of loads

H+: P[starved] ≥ 0.0015 against H−: P ≤ 0.0005, with α = β = 0.05/32 per test. Queue capacity 64, at
64–512 cores, over 8 load corners: ρ₁, ρ₂ ∈ {0.5, 0.7} and ρ_m ∈ {0.05, 0.3}.

- **Decisions.** All 32 tests: **H−** (P < 0.0005 at each configuration, family-wise error 0.05),
  each after 6,454 runs.
- **Starved windows.** None occurred in any of the 206,528 runs.
- **Runs and time.** 206,528 runs against 1,094,304 for the fixed-sample design (5.3×): 49 minutes of
  simulation instead of an estimated 4.4 hours.
- **Compared with Clopper–Pearson.** With no violations at all, SPRT stops at the same point as a
  zero-failure Clopper–Pearson certificate (ln(1/α)/θ = 6,462 runs at θ = 0.001; SPRT 6,454). Here,
  SPRT gains nothing over that certificate. The pre-registration said so.

## Reading

- **What SPRT gave.** It paid off where the truth was far from the threshold at a moderate
  probability. Family A decided in about 500 runs a claim whose fixed-sample design needs 10,597 runs.
  At a rare threshold with zero violations (family B), SPRT is only as good as the zero-failure
  certificate, as expected.
- **What scale gave.** Building and running models with up to 200,459 state variables costs seconds to
  minutes. The step is generated from the program's structure (design decisions 54–55): before that,
  the limit was 16 cores at capacity 32, about 3,300 variables.
- **What was scaled.** The total offered load stays fixed as cores are added (each core's flows send
  at ρ/NC), so the bottleneck is the same link at every size. The study scales the model's size, not
  the difficulty of the contention, which is also why small sizes predicted the large ones.
- **Limits.** The claims hold for the registered configurations only: the MQPrio corner and the 8
  load corners of the grid. "Across all traffic" would need a maximum over inputs, which sampling
  cannot certify. Family B's single violation-free outcome also fits a policy that cannot starve at
  all. Proving that for every input would be a job for Z3, which does not scale to these sizes.
