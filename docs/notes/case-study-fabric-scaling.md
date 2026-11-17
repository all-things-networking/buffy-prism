# Case study: does the approach scale? Incast in a leaf-spine fabric

*Model: `buffy/examples/jani/fabric.buffy` (Buffy branch `fabric-scaling`). Scripts and raw results:
`experiments/buffy_fabric/` (run all with `run_study.sh`). One core of an 8 GB laptop, one model at a time.*

*Machine and implementation.* The measurements come from a modest machine (an 8 GB laptop, one core) and a
research prototype: an unoptimised compiler and a simulator with no parallelism. Where a run hit this
machine's limits, the note marks it **[machine-bound]**. Such a limit belongs to this laptop and prototype, not
to the technique. A workstation with more memory, or the compiler change named in decision 56, would move it.

## Why this study

The SPRT study on Loom (`sprt-loom-results.md`) certified claims at 200,000 state variables, but it grew
only the model. The total offered load stays fixed as cores are added, so the bottleneck is the same link
at every size and small sizes predict large ones. Reviewers will rightly ask whether the approach handles
problems whose *difficulty* grows with their size. This study uses such a model and measures each step of
the pipeline along three axes:
- fabric size;
- horizon;
- the rarity of the bad event.

## The model

A leaf-spine fabric with:
- NL leaves (top-of-rack switches), each with H hosts;
- NS spines, with a link from every leaf to every spine;
- every link and every NIC moving one packet per step;
- output-queued switches with capacity B per output port, and NIC queues of capacity 8;
- ECMP over the spines, per packet by default (per flow with `ECMP = 1`).

Three kinds of traffic:
- **Incast (partition/aggregate).** Every query round (every PERIOD steps), host 0 queries *every* host on
  the other leaves. Each responder sends SLEN = 4 packets after a delay drawn uniformly from 0..10. The
  fan-in is M = (NL − 1)·H − 1, so **the load on the aggregator grows linearly with the number of hosts**.
  Unlike Loom, the contention grows with the model.
- **Victim.** A flow from host 0 of leaf 1 to host 1 of leaf 0, the aggregator's rack neighbour, at load
  0.3. It never crosses the aggregator's port, but it shares leaf 1's uplinks and the spines' links to
  leaf 0 with the incast.
- **Background.** Every host sends at load 0.05 to a uniformly random host on another leaf.

Bad events, per query round:
- `loss`: at least THRESH incast packets are lost;
- `victim`: the victim loses at least VTH packets (collateral damage).

Counters of lost and delivered packets and of bad rounds support expected values and rates.

Two modelling points matter.
- **Arbitration.** When several inputs send into one output queue in the same step, they are admitted
  in a random rotation of their order, redrawn every step. A first version used the fixed order of the
  program's loops. That gave the victim, the first host of the first loaded leaf, every freed slot, so
  it never lost a packet at any size. No real output-queued switch behaves like that.
- **Compile cost.** The rotation is written as two passes in fixed order, so that every buffer index
  stays a constant of the loop. A rotated index `(i + r) % NL` would make the compiler consider every
  element at each access, which was quadratic in compile time.

At the default size (3 leaves, 2 hosts, 2 spines) the program has 180 state variables. The size sweep
below uses B = 16.

## Validation

- **Independent oracle** (`fabric_oracle.py`). A Python simulation written from the model's description,
  not from the program. The native simulator and the oracle agree on 12 configurations, from 6 to 64
  hosts. Each configuration has 9 quantities: P[loss], P[victim], and the means of 7 counters. With
  100,000 runs on each side, the largest |z| is 2.25 over 108 comparisons; the Bonferroni bound at 0.05
  is 3.55 (`results/oracle_check.log`). Four of the configurations have 32–64 sources per step; they were
  added after the bug below.
- **Structured vs unrolled step** (`tests/test_native_structured.py`, now with two fabric variants). The
  default and both variants give identical successors on 960 random-walk states each. The fabric's
  steps are too large to enumerate, so these are compared at sampled uniforms through
  `JaniModel.step(s, e, u)`. That single-uniform path is the one the precision fix does not cover, so on
  the 4×4×4 variant the later sources are compared almost only on their first outcome. The oracle check
  is the stronger evidence for the structured core. The JANI-path
  simulator cannot load the model (too many joint destinations per step), so `test_native_target.py`
  does not cover it.

### Two defects found and fixed on the way

1. **The native simulator's draws collapsed in steps with many random sources.** It may affect
   earlier results; see "Who else is affected" below.
   - **Cause.** `jm_step_r` drew all of a step's sources from one double, rescaled into each chosen
     interval. That is exact for real numbers, but each rescaling spends log2(1/q) of the 53 bits. After
     about 45 bits, the later sources collapsed onto their first outcomes.
   - **How it showed.** At 8×8×4 the four uplinks of a leaf held on average 17.5 / 5.5 / 9.1 / 5.5
     packets instead of 9.2 each. The oracle disagreed by many standard errors. The structured and
     unrolled cores still agreed, because both use the same runtime.
   - **Fix.** The batch paths now pass their generator, and a fresh uniform replaces the residual once it
     has been rescaled by 2^8. That is exact, since the residual is uniform and independent of the
     earlier choices. Steps that never rescale that far draw exactly as before.
   - **Regression test.** `tests/test_native_precision.py` (64 uniform and 64 rare Bernoulli sources per
     step) gives |z| = 1.9 with the fix and 346 without it. Only its uniform half has power: the audit
     found that the Bernoulli half also passes before the fix.
   - **Who else is affected.** The collapse needs many draws with power-of-two probabilities. Rescaling
     by a dyadic interval shifts real bits out of the double, while rescaling by a non-dyadic one rounds
     and refills the low bits. The fabric's uniform draws over 2, 4, 8 or 16 spines and hosts are
     dyadic. The audit ran Loom-like steps (512 Bernoulli sources at total rates 1.0–2.0, up to 2 million
     steps) through a pre-fix copy of the runtime. The distribution of the number of arrivals matched
     the exact one within sampling error, with a largest deviation of −2.1σ on one tail probability.
     That is a proxy, not the Loom model. Loom's SPRT results predate the fix, so its Family B (H−, no
     violations, the direction in which suppressed bursts would be anti-conservative) should be re-run
     for completeness. `JaniModel.step(s, e, u)` still takes the unrefreshed path.
2. **Elaboration was quadratic in the number of draws** (Buffy design decision 56).
   - **Cause.** The interval map for dynamic indices was rebuilt for every new traffic source (every
     draw in a loop adds one). Separately, an opaque value was interned per FIFO slot per append.
   - **Effect of the fix.** The output is byte-identical. The fabric at 1,024 hosts compiled in 43 s
     before and 5.5 s after (before the arbitration change).

The other test suites pass with both fixes: the native tests (checks, policy, rewards, conditioning,
tables, JANI) and Buffy's JANI suite. Buffy's suite uses Storm only on its small reference examples.

## Axis 1: fabric size

4:1 oversubscription (H = 4·NS), B = 16, T = 60 (one round), THRESH = 10, VTH = 1. Each size runs in its
own process, one after the other (`size_sweep.py`, `results/size_sweep.jsonl`). The SPRT tests the claim
"the victim loses a packet in more than 10% of rounds": H+: P ≥ 0.12 against H−: P ≤ 0.08, with
α = β = 0.01. The fixed-sample test for the same α, β and δ needs 1,203 runs.

| fabric (NL×H×NS) | hosts | fan-in | state vars | compile | compiler peak memory | build | per run | per host-step | P[victim] (95% CI) | incast lost | SPRT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2×8×2 | 16 | 7 | 692 | 0.1 s | 28 MB | 1.1 s | 0.15 ms | 158 ns | 0.0024 [0.0015, 0.0036] | 0.03% | H− (104 runs) |
| 3×8×2 | 24 | 15 | 1,032 | 0.1 s | 33 MB | 0.5 s | 0.23 ms | 162 ns | 0.230 [0.222, 0.239] | 16% | H+ (63) |
| 4×8×2 | 32 | 23 | 1,372 | 0.1 s | 40 MB | 0.7 s | 0.31 ms | 162 ns | 0.763 [0.755, 0.772] | 43% | H+ (16) |
| 6×8×2 | 48 | 39 | 2,052 | 0.2 s | 53 MB | 0.7 s | 0.47 ms | 164 ns | 0.944 [0.939, 0.948] | 66% | H+ (12) |
| 8×8×2 | 64 | 55 | 2,732 | 0.3 s | 68 MB | 0.7 s | 0.65 ms | 170 ns | 0.976 [0.973, 0.979] | 75% | H+ (12) |
| 8×16×4 | 128 | 111 | 5,452 | 0.6 s | 146 MB | 1.0 s | 1.5 ms | 197 ns | 0.978 [0.975, 0.981] | 87% | H+ (12) |
| 16×16×4 | 256 | 239 | 10,892 | 1.6 s | 287 MB | 2.6 s | 3.0 ms | 197 ns | 0.997 [0.996, 0.998] | 94% | H+ (13) |
| 16×32×8 | 512 | 479 | 21,772 | 5.2 s | 732 MB | 4.5 s | 6.6 ms | 215 ns | 0.997 [0.996, 0.998] | 97% | H+ (12) |
| 32×32×8 | 1,024 | 991 | 43,532 | 15 s | 1.2 GB | 12 s | 13.7 ms | 223 ns | 0.9992 [0.998, 0.9997] | 98.5% | H+ (12) |
| 64×32×8 | 2,048 | 2,015 | 87,052 | 51 s | 2.4 GB | 31 s | 31.4 ms | 256 ns | 0.9995 [0.998, 0.9999] | 99.3% | H+ (12) |

**One size further: 4,096 hosts** (64×64×16; `try_largest.sh`, `largest_run.py`, `results/largest.jsonl`).
**[machine-bound]** The compile paged: its footprint was more than twice this laptop's memory. It compiled
alone. The 6 GB watchdog in `try_largest.sh` polls resident memory, so it could not see
memory paged out, and it never fired.
- **Model.** 174,092 state variables, 68 MB of JANI, 28 MB of C.
- **Compile.**
  - It took 21 minutes of wall time, against 4.5 minutes of user CPU. The machine was paging: 7.8 minutes
    went to the kernel. The compiler's peak memory footprint was **18.6 GB** (with `--stats`), of which
    only 3.4 GB was resident on this 8 GB machine (`results/largest_compile.log`).
  - Even counting user CPU alone, that is 5.3 times the 51 s at 2,048 hosts, for twice the model.
    Memory grew about 7.6 times for that doubling.
- **Build and simulation.** Clang took 113 s (3.7 times the 2,048-host build, for 2.2 times the C). A run takes 57 ms, which is 232 ns per host-step, in line
  with the sweep, and the simulator's process peaked at 1.3 GB.
- **Answer.** P[victim] = 1.000 [0.998, 1] over 1,931 runs, and 99.6% of the incast is lost. The SPRT
  decides H+ in 12 runs, its minimum. The 11 s is one batch of 200 runs, the sampler's batch size.
- **Where the size limit is.** Everything after compilation stays cheap at this size. Compilation is
  what stops it **on this machine** [machine-bound]: at 4,096 hosts the prototype compiler already needs
  more than twice the laptop's 8 GB.
  Larger sizes need the next step of decision 56, which is not to build the unrolled DAG.

**Reading.**
- **The answer changes with size, unlike Loom.** Between 16 and 48 hosts, P[victim] goes from 0.002 to
  0.94: incast collateral damage switches on as the fan-in grows. The share of the incast that is lost
  keeps growing up to 2,048 hosts, because the aggregator's port delivers about 56 packets per round
  whatever the fan-in. A result at 16 hosts says nothing about 64. Here, scale has to be analysed, not
  extrapolated.
  - The change happens between 16 and 64 hosts. Above that the answer is saturated, and the port's
    capacity explains it: the lost share is about 1 − 56/(4M), which gives 0.9931 against the measured
    0.9927 at 2,048 hosts. P[victim] follows the number of leaves more than the number of hosts.
  - So the model shows that small sizes can mislead. It does not show a surprise at the largest
    size.
- **Simulation scales linearly.** The cost per host-step grows only from 158 ns to 256 ns between 16
  and 2,048 hosts, about hosts^1.1 (the cause is not measured). A run of 60 steps at 2,048 hosts takes 31 ms.
- **Compilation is the steepest step.**
  - Compile time grows faster than the model: ×3.3 from 1,024 to 2,048 hosts, and ×4.3 to 4,096.
  - Compiler memory is linear: 0.24 GB at 1,024 hosts, 0.49 GB at 2,048 and 0.94 GB at 4,096 (peak
    footprint). This holds since the compiler stopped building the step DAG for the native target
    (compiler decision 57). The DAG grew roughly as variables^1.4, from 0.67 M nodes at 256 hosts to
    34.9 M at 4,096, and the compile needed 4.7 GB at 2,048 hosts and 18.6 GB at 4,096.
  - The excess comes from the program's dynamic-index fan-out: each access is expanded over the elements
    it can reach (the spine's port for a random destination leaf reaches NL of them). It also comes from
    the elaborator building the whole unrolled DAG, which the structured target does not emit.
  - The next compiler step is to skip that DAG for `--target native` (decision 56).
- **Sequential tests.**
  - From 48 hosts up, the test stops at its minimum of 12 runs (P ≈ 1). At 16 hosts it stops at the
    minimum for H−, 104 runs without a loss. Only 3×8×2 (P = 0.23, 63 runs) lies in between.
  - None of these sizes puts P near the threshold. There, the SPRT's expected run count (about 1,170
    at P = 0.10) equals the fixed-sample test's 1,203. So this sweep shows that the run count does not
    grow with model size at the two floors, not across the whole range of P.
  - At 2,048 hosts the test took 6.6 s, which is one batch of 200 runs.

## Axis 2: horizon

256 hosts (16×16×4, B = 16), a query round every 60 steps, VTH = 10: a round in which the victim loses
at least 10 packets has p ≈ 0.019. Horizons run from one round (60 steps) to 167 rounds (10,020 steps);
see `horizon_sweep.py` and `results/horizon_sweep.jsonl`. P_T is the probability of at least one such
round within T. The SPRT tests P_T ≥ 0.5 (δ = 0.05, α = β = 0.01).

| T | rounds | per run | per step | P_T (95% CI) | 1 − (1 − 0.0192)^rounds | runs for P_T ± 10% | per-round rate | runs for rate ± 10% | steps for rate ± 10% | SPRT |
|---|---|---|---|---|---|---|---|---|---|---|
| 60 | 1 | 3.5 ms | 58 µs | 0.0192 [0.0178, 0.0207] | 0.0192 | 19,615 | 0.0192 | 19,615 | 1.18 M | H− (23 runs) |
| 180 | 3 | 10.2 ms | 57 µs | 0.057 [0.053, 0.061] | 0.057 | 6,373 | 0.0193 | 6,504 | 1.17 M | H− (27) |
| 600 | 10 | 42 ms | 70 µs | 0.178 [0.165, 0.191] | 0.176 | 1,779 | 0.0190 | 1,917 | 1.15 M | H− (35) |
| 1,800 | 30 | 105 ms | 58 µs | 0.437 [0.409, 0.466] | 0.441 | 495 | 0.0190 | 663 | 1.19 M | H− (109) |
| 6,000 | 100 | 363 ms | 61 µs | 0.883 [0.847, 0.914] | 0.856 | 51 | 0.0194 | 180 | 1.08 M | H+ (35) |
| 10,020 | 167 | 506 ms | 51 µs | 0.975 [0.946, 0.991] | 0.961 | 10 | 0.0192 | 113 | 1.13 M | H+ (25) |

**Reading.**
- **Cost per step is flat** at 50–70 µs for 256 hosts. The compile (about 2 s) and the build (about
  3 s) do not depend on T.
- **For rates, the work stays constant.** Estimating the per-round rate to ± 10% takes about 1.1–1.2
  million simulated steps at every horizon (about 65 s here). Long runs need proportionally fewer of
  them, because rounds are nearly independent: P_T matches 1 − (1 − p)^rounds, and the per-round
  variance ratios are 0.93–1.01. The victim's path is back at its steady state about 10 steps before
  the next round. The aggregator's own port is not drained: at the round boundary it is non-empty in 96%
  of runs, with 2.9 packets on average.
- **For "within T" probabilities, the question itself changes with T.** P_T grows from 0.02 to 0.97,
  and the runs needed depend on how far P_T is from the threshold. The SPRT needed most runs (109) at
  T = 1,800, where P_T ≈ 0.44 sits next to the indifference region (0.45–0.55).
- **Horizon is not a scaling problem for simulation.** It is for exact methods, whose unrolled state
  space grows with T.

## Axis 3: a rarer bad event

A small fabric (2×8×2, B = 16, one round of 60 steps) and `loss` with THRESH = 6, where P ≈ 6·10⁻⁶.
Monte Carlo on the native simulator is compared with its RESTART and fixed-effort splitting, each over
three seeds (`rare_event_seeds.py`, `results/rare_event_seeds.jsonl`; every run's estimate is saved in
`results/rare_event_runs/`).

- **Levels.** Expected success picks levels and factors from pilot runs (`splitting.py`), with the
  weighted pilot estimator described below. One pilot per importance function; its time is charged to
  every seed.
- **Derived importance** (`--auto-importance`): min(odrops, 6), the query's progress.
- **Refined importance:** the derived one plus the aggregator port's backlog, min(odrops, 6)·17 +
  backlog(eg[0]).
- **Budget.** Each (importance, method, seed) runs for 300 s in batches of about 20 s. Fixed effort
  uses 1,000 trajectories per level.
- **Target.** A 95% interval with ± 10% relative half-width. Each cell's time for that scales its
  measured time by (observed half-width / 10%)², plus the whole pilot. Monte Carlo's time is
  extrapolated from its measured cost per run (152 µs) at the pooled P.

| importance | pilot | method | estimates, seeds 1–3 (·10⁻⁶) | ± per seed | top-5 share per seed | time for ± 10% per seed | speed-up over Monte Carlo per seed | three seeds pooled |
|---|---|---|---|---|---|---|---|---|
| — | — | Monte Carlo | 6.3 (5 hits in 800,000 runs, 122 s) | — | — | 9,130 s (60 M runs) | 1× | — |
| derived, 6 levels | 157 s; P̂ 6.4·10⁻⁶; factors [139, 3, 4, 5, 4, 5] | RESTART | 5.6, 6.1, 5.2 | 35% | 0.30–0.32 | 3,780–3,900 s | 2.34–2.42× | 5.6·10⁻⁶ ± 20%; 2.4× |
| derived, 6 levels | same | fixed effort | 6.5, 5.1, 6.4 | 33–35% | 0.29–0.33 | 3,330–3,810 s | 2.39–2.74× | 6.0·10⁻⁶ ± 19%; 2.6× |
| refined, 15 levels | 50 s; P̂ 1.1·10⁻⁵; factors 2–3 per level | RESTART | 7.3, 6.5, 5.5 | 27–44% | 0.21–0.40 | 2,210–5,990 s | 1.52–4.13× | 6.4·10⁻⁶ ± 20%; 2.5× |
| refined, 15 levels | same | fixed effort | 10.4, 6.3, 6.0 | 54–75% | 0.57–0.62 | 8,750–16,750 s | 0.54–1.04× | 7.6·10⁻⁶ ± 40%; 0.6× |

- **Consistency.** The twelve splitting estimates are homogeneous (χ² = 5.5 on 11 degrees of freedom,
  p = 0.91) and their equal-weight mean is 6.42·10⁻⁶ ± 0.40·10⁻⁶. Monte Carlo's 5 hits agree with it
  (binomial p = 0.82).
- **Factors are now right.** The factor product times P is 1.07 for the derived importance and 0.71
  for the refined one, so a RESTART root run reaches the goal about once on average, as intended. The
  refined pilot (256 pilots at effort 256) over-estimated P by 1.6×; the derived pilot (256 at effort
  1,024) was within 1%.
- **Equal cost per step.** Every method simulated about 121 M steps per 300 s, the same rate as Monte
  Carlo. The gain is entirely variance reduction per step.
- **Heavy tails.** Within one 300 s seed the top 5 runs carry 21–40% of the sum for RESTART and for
  derived fixed effort, and about 60% for refined fixed effort. Per-seed intervals are therefore
  indicative only; the pooled column (three seeds, 0.9 M CPU-seconds per method) is the better figure,
  with top-5 shares of 0.13–0.16 (0.37 for refined fixed effort).
- **Machine.** The absolute times are for one core of this laptop [machine-bound]. Every method here is
  a set of independent runs and parallelises across cores; the speed-up ratios do not depend on that.

**The pilot estimator, fixed.** `expected_success` used to average each level's success fraction over
the pilots that reached the level, weighting them equally. The independent audit showed that this is
biased low at the upper levels, and the bias compounds per level.
- The cause: a pilot's fixed-effort weight and its next fraction are positively correlated. "Hot"
  entrance states (an incast still filling the queues) succeed at every level.
- The check that failed: the level probabilities must multiply to P. They multiplied to 2.1·10⁻⁷ for
  the derived importance and 3.1·10⁻¹⁵ for the refined one, against P ≈ 6·10⁻⁶.
- The fix: weight each pilot's fraction at level l by the product of its fractions below l (its
  fixed-effort weight). The product of the estimates then equals the mean fixed-effort estimate of P.
  Rounding a level's factor now carries multiplicatively into the next level, so the factors multiply
  to about 1/P̂. In this rerun the derived pilot's level probabilities are 0.0072, 0.29, 0.26, 0.22,
  0.23 and 0.23, with product 6.4·10⁻⁶.

**History: the first, single-seed run** (`rare_event.py`, `results/rare_event.jsonl`). It used the
biased pilot.
- Derived importance: RESTART with factors [133, 3, 5, 7, 12, 25], over-split about 25 times, gave
  6.2·10⁻⁶ ± 26% (1.7× over Monte Carlo); fixed effort gave 6.0·10⁻⁶ ± 21% (2.7×). Monte Carlo had 32
  hits in 7 M runs (4.6·10⁻⁶).
- Refined importance: the biased factors multiplied to 5.3·10¹³ against 1/P ≈ 1.7·10⁵, about 4·10⁸
  expected goal hits per root run. RESTART was stopped after 2 h 50 min of CPU in its first batch of
  2,000 runs; the script then checked its time budget only between batches, which `rare_event_seeds.py`
  no longer does. An earlier version of this note blamed the importance's non-monotone shape; the
  audit refuted that. The audit's one short rerun with weighted factors reached about 3.6×, within the
  seed-to-seed range now measured (1.5–4.1×).

**Reading.**
- **Splitting works here, but only modestly: about 2.5× over Monte Carlo.** With the derived
  importance the gain is stable across seeds (2.3–2.7×) and the same for RESTART and fixed effort. At
  P ≈ 6·10⁻⁶ that still means about an hour of one core for ± 10% on a 16-host fabric, against about
  2.5 hours for Monte Carlo.
  - Almost all of the rarity sits in the first drop: P(odrops ≥ 1) ≈ 0.0072 in one round.
  - Each further level cuts the probability by only 3.5 to 4.5 times, so there are few levels to
    split over. Their retrials share the entrance state, and whether they succeed depends on the
    queues' contents, which the derived importance does not see.
  - Measured directly, fixed effort with levels 1–3 agrees with Monte Carlo on P(odrops ≥ 4)
    (1.38·10⁻⁴ ± 1.5·10⁻⁵ against 1.42·10⁻⁴), with the same per-level conditionals.
- **The refined importance does not help.** With correct factors, RESTART on it matches the derived
  importance when pooled (2.5× against 2.4×), with a wider spread across seeds (1.5–4.1×). Fixed effort
  on its 15 levels is worse than Monte Carlo (0.6×): with 1,000 trajectories per level, the variance
  compounds over more levels, and the estimates are dominated by a few runs. Adding the backlog sees
  the event's effect at one port, not its cause.
- **What this says about scale.** Splitting's gain depends on the importance function, not on the
  model's size. Both importance functions here are cheap to compute at any size. The event's cause is
  a joint pattern of many responders' delays and ECMP choices filling one port. An importance function
  that looks ahead over the incast still in flight remains a modelling task, as does validating
  whether such a function helps.

## Which steps scale, and which do not

| step | scales here? | evidence |
|---|---|---|
| Modelling | yes | One parameterised Buffy program, 180 to 174,092 state variables. Arbitration and indices must be written so that every access reaches a few elements. |
| Compile (`--target native`) | yes in memory (linear); time superlinear in the prototype | 16 s and 0.49 GB at 2,048 hosts, 69 s and 0.94 GB at 4,096 (174,092 variables). Two quadratic costs were removed (decision 56), and the unrolled DAG is no longer built (decision 57). It had needed 18.6 GB and 21 min of paging at 4,096 hosts. The remaining excess in time is the dynamic-index fan-out: each access visits every element it can reach. A run at 4,096 hosts takes 57 ms, and the SPRT decides in 12 runs. |
| Build (clang) | yes, mildly superlinear | 31 s for 13 MB of C at 2,048 hosts; 113 s for 28 MB at 4,096. |
| Simulation | yes, linear in hosts × steps | 158–256 ns per host-step from 16 to 2,048 hosts, 50–70 µs per step at 256 hosts for any T up to 10⁴. Needed one runtime fix for steps with many draws. |
| Sequential tests (SPRT) | yes, at the floors measured | Runs did not grow with model size or horizon: 12–109 runs here. In the size sweep every decision is at or near the test's minimum (12 for H+, 104 for H−), so a test near the threshold on a large model is still to be shown. Rate estimates cost a constant number of simulated steps across horizons. |
| Rare events (splitting) | modestly; depends on the importance function | About 2.5× faster than Monte Carlo at P ≈ 6·10⁻⁶, over three seeds (2.3–2.7× per seed with the derived importance), with RESTART or fixed effort. Needed a fix to the pilot estimator, whose bias had stalled RESTART. A refined importance (with the aggregator's backlog) did not help. Absolute times are one core of this laptop [machine-bound]; the ratios are not. |
| Exact conditioning (`--condition-on`) | no (argued, not attempted) | The input process here has dozens to thousands of sources per step (four per host plus one per link). On-demand conditioning memoises h over the input states that runs reach. The responders' start delays alone give 11^M joint values at the first step: 2·10⁷ at 16 hosts (M = 7) and 9·10²³ at 32 hosts (M = 23). Conditioning on one source (e.g. the victim's arrivals) remains feasible; joint conditions over the incast do not. |
| Learning conditions over many sources | no (not attempted) | The learner (case studies B, C, F) searches conditions over the histories of one or two sources. Here the cause of collateral damage is a joint pattern over hundreds of responders' delays and ECMP choices. The hypothesis space grows exponentially in the sources, and so does the run count needed to certify a condition with small probability mass. |
| Exact model checking (Storm, mcsta) | no (not attempted, by policy) | The delay vector above alone bounds the reachable states from below by 2·10⁷ at 16 hosts and 9·10²³ at 32 hosts, before any queue contents; the state space also grows with the horizon. Exact checking is limited to the small reference examples of Buffy's test suite. |

## Conclusion

- **What scales.** Along every axis tried, the simulation-based pipeline scales to an industrial-size
  instance on a laptop: compile, build, simulate and sequentially test. At 2,048 hosts the fabric is a
  model of 87,052 state variables whose contention grows with size. It compiles in 16 s, a run
  costs 31 ms, and a sequential test decides in seconds. At 4,096 hosts (174,092 variables) the compile
  takes 69 s and 0.94 GB, and everything after it is just as cheap.
- **What the answers show.** Unlike Loom, the answers change with size: collateral damage from incast
  appears between 16 and 48 hosts and is nearly certain beyond. Small sizes can mislead, so the
  ability to analyse the instance of interest directly matters. Above 64 hosts, though, the answer is
  saturated and follows from the port's capacity.
- **The limits are elsewhere.**
  - Compile time, which grows with the dynamic-index fan-out (each access visits every element it
    can reach), and the C build (113 s at 4,096 hosts).
  - Rare events. The gain from splitting was modest here: about 2.5× over Monte Carlo, stable over
    seeds once the pilot estimator was fixed. A larger gain needs an importance function that sees the
    incast's cause, which is a modelling task.
  - Every exact technique: exact conditioning or learning over many sources, and exact model checking.
    These remain tools for small configurations and single sources.
- **A caveat on earlier results.** This study also found a sampling defect in the simulator, in steps
  with many power-of-two draws. On Loom-like Bernoulli steps the audit found no measurable effect. Loom's
  Family B is still worth re-running with the fixed runtime, for completeness.

## Independent audit (2026-11-11)

An independent auditor checked the note against its code, raw results and published references
(`experiments/buffy_fabric/audit-report.md`). It
recomputed every table cell from the jsonl files and spot-checked the model with the oracle at the
study's base configuration: 3×8×2 gives victim 0.2314 against 0.2302. It agreed with the size and
horizon conclusions, the model's validity and the RNG fix. Its three main disagreements are reflected
above:
1. The RESTART stall was caused by a biased pilot estimator, not by the importance's shape.
2. Compiler memory at 4,096 hosts was 18.6 GB, not 3.4 GB.
3. The Loom caveat's mechanism did not hold on Loom-like steps.

Follow-ups, in its order:
1. Fix `expected_success` with the weighted estimator, a check of the factor product against 1/P̂, and
   an in-batch time check. Then redo axis 3 over several seeds, saving the per-run estimates.
   **Done:** axis 3 above (three seeds, factor product × P of 1.07 and 0.71, batches of about 20 s).
   The legacy `src/netmdp/sampler/splitting/expected_success_method.py` is not changed.
2. Measure compiler memory by footprint at every size, and make the watchdog use it.
3. Add a size sweep whose answer is not saturated (per-port load held near critical), so the SPRT is
   exercised near its threshold on a large model.
4. Re-run Loom's Family B with the fixed runtime.
5. Close the test gaps: the precision test's Bernoulli half, `JaniModel.step`'s unrefreshed path, and
   the base configuration and a mid-tail quantity in the oracle check.
6. Re-measure efficiency figures from other users of `expected_success`
   (`tests/native_*_experiment.py`).
