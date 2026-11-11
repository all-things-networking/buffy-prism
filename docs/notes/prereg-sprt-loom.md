# Pre-registration: sequential certification of Loom tenant isolation at scale

*Status: registered on 2026-11-11, approved by the study's author. This file and
`experiments/buffy_fperf/prereg_sprt.json` are committed before any of the runs below, and that
commit is the timestamp of the registration. Nothing in either file changes after it; deviations go
in a separate results note.*

## Why

Buffy's structured native step now compiles Loom with 512 cores and queue capacity 64 in about 15 s.
Each run of such a model costs milliseconds. A claim about the model is therefore cheap to test only if
the test needs few runs. Wald's SPRT decides "P ≥ θ + δ" against "P ≤ θ − δ" with error rates α and β,
and needs few runs when the truth is far from θ. A fixed-sample test with the same α, β and δ needs a
number of runs fixed in advance, and that number grows as 1/δ². This study checks two claims at sizes
never simulated, records how many runs SPRT needed, and compares that with the fixed-sample design.

## What has and has not been seen

- **Seen during development** (so these sizes are not used here): Loom MQPrio at the box corner
  ρ = (0.6, 0.6, 0.1) with queue capacity 10 (4 and 8 cores) and capacity 32 (4 to 256 cores); the
  hierarchical policy at capacity 10 and 32 (0 starved windows in every run).
- **Not seen:** any simulation at queue capacity 64. A compile of 256 and 512 cores at capacity 64 was
  run to check feasibility. It simulated nothing.

## Model and event

- **Model.** `buffy/examples/jani/loom_isolation.buffy`, compiled with `buffyc-mc --target native
  --stop-at-horizon`, with the defaults T = 60, W = 20, SHARE = 40 and ENQ = 4, and with the overrides
  below.
- **Starved window.** Tenant 1 has packets waiting at every step of the last W steps, yet receives at
  most SHARE% of the W deliveries (`loom_eval.py`: `waiting and 100·w1 ≤ SHARE·W`).
- **One run** is one Bernoulli sample of "starved".

## Hypotheses

**Family A: MQPrio's isolation failure persists at scale.**

| | |
|---|---|
| configurations | CAP = 64, POLICY = 0, ρ = (0.6, 0.6, 0.1), NC ∈ {64, 128, 256, 512} (4 tests) |
| test | SPRT of H+: P ≥ 0.31 against H−: P ≤ 0.29 (θ = 0.30, δ = 0.01) |
| errors | α = β = 0.0125 per test (Bonferroni: family-wise 0.05) |
| prediction | H+ at every configuration (smaller sizes gave 0.37–0.41) |
| truncation | 10,597 runs: the fixed-sample test with the same α, β, δ; if reached, the test is inconclusive |

**Family B: the hierarchical policy keeps a starved window below 1 in 1,000 across a grid of loads.**

| | |
|---|---|
| configurations | CAP = 64, POLICY = 1, NC ∈ {64, 128, 256, 512} × ρ₁, ρ₂ ∈ {0.5, 0.7} × ρ_m ∈ {0.05, 0.3} (32 tests) |
| test | SPRT of H+: P ≥ 0.0015 against H−: P ≤ 0.0005 (θ = 0.001, δ = 0.0005) |
| errors | α = β = 0.05 / 32 = 0.0015625 per test |
| prediction | H− at every configuration |
| truncation | 34,197 runs (the fixed-sample test); if reached, inconclusive |

"Across a grid" is the claim: the 32 configurations, not every possible traffic pattern. A bound over
all inputs is a maximum over inputs, which sampling cannot certify.

## Procedure

- **Runs.** Each test gets its own random stream, with seed 20261111 + its index in
  `prereg_sprt.json`. Runs are simulated in batches of 200. The SPRT's log-likelihood ratio is updated
  run by run, in order, and the test stops at the first run where it crosses a boundary. Runs after
  that one in the same batch are discarded unseen: they are not counted, used or reported.
- **Order.** Family A first, then family B, each in the order of `prereg_sprt.json`. Every test is run
  to its decision or its truncation. None is repeated or rerun with another seed.
- **Recorded for every test:**
  - the decision (H+, H− or inconclusive);
  - the number of runs at the decision, with the sample mean (not an estimate with an interval);
  - wall-clock time;
  - the Buffy compile and simulator build times.
- **Comparison, reported but not part of any decision:**
  - the fixed-sample n above;
  - for family B, the zero-failure Clopper–Pearson certificate (ln(1/α)/θ = 6,462 runs if no
    starved window occurs).

  With a true rate near 0, family B's SPRT needs about as many runs as that certificate (about 6,450),
  so its advantage over Clopper–Pearson is small there. Family A is where SPRT should save most:
  about 580 runs on average at a true 0.38, against 10,597.

## Expected cost

At capacity 64 a run should cost about 2–4 times its capacity-32 cost, which was 2.1 ms at 64 cores
and 7.6 ms at 256.

| family | SPRT | fixed-sample design |
|---|---|---|
| A | minutes | about 1 hour |
| B | about 1 hour | about 5 hours |

## Tools

- **Buffy:** branch `outcast-case-study`, commit `5ed2f76`.
- **buffy-prism:** branch `claude/buffy-to-jani-compiler-de318b`, at the commit that registers this file.
- **SPRT runner:** `experiments/buffy_fperf/sprt_loom.py`, written after registration. It reads only
  `prereg_sprt.json`. Its SPRT is `src/netmdp/hyptest/wald_sprt.py`'s, with the run-by-run truncation
  above.
