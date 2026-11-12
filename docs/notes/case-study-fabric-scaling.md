# Case study: does the approach scale? Incast in a leaf-spine fabric

*Model: `buffy/examples/jani/fabric.buffy` (Buffy branch `fabric-scaling`). Scripts and raw results:
`experiments/buffy_fabric/` (run all with `run_study.sh`). One core of an 8 GB laptop, one model at a time.*

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
  default and both variants give identical successors on 960 random-walk states each. The JANI-path
  simulator cannot load the model (too many joint destinations per step), so `test_native_target.py`
  does not cover it.

### Two defects found and fixed on the way

1. **The native simulator's draws collapsed in steps with many random sources.** This bug affects
   earlier results; see the note in the shared folder.
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
     step) gives |z| = 1.9 with the fix and 346 without it.
   - **Who else is affected.** Any model whose steps spend more than about 45 bits, e.g. Loom at hundreds
     of cores in steps with 4 or more arrivals. **The Loom SPRT results at 64–512 cores were produced
     before this fix and should be re-run.** The bias is small for those claims (it suppresses arrivals at
     the later cores in about 1% of steps), but it is not zero.
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
It compiled alone under a 6 GB memory watchdog.
- **Model.** 174,092 state variables, 68 MB of JANI, 28 MB of C.
- **Compile.**
  - It took 21 minutes of wall time, against 4.5 minutes of user CPU. The machine was paging: 7.8 minutes
    went to the kernel, and the compiler's peak resident memory was 3.4 GB on an 8 GB machine.
  - Even counting user CPU alone, that is 5.3 times the 51 s at 2,048 hosts, for twice the model.
- **Build and simulation.** Clang took 113 s. A run takes 57 ms, which is 232 ns per host-step, in line
  with the sweep, and the simulator's process peaked at 1.3 GB.
- **Answer.** P[victim] = 1.000 [0.998, 1] over 1,931 runs, and 99.6% of the incast is lost. The SPRT
  decides H+ in 12 runs, in 11 s.
- **Where the size limit is.** Everything after compilation stays cheap at this size. Compilation is
  what stops it: doubling once more would not fit in memory without the change of decision 56.

**Reading.**
- **The answer changes with size, unlike Loom.** Between 16 and 48 hosts, P[victim] goes from 0.002 to
  0.94: incast collateral damage switches on as the fan-in grows. The share of the incast that is lost
  keeps growing up to 2,048 hosts, because the aggregator's port delivers about 56 packets per round
  whatever the fan-in. A result at 16 hosts says nothing about 64. Here, scale has to be analysed, not
  extrapolated.
- **Simulation scales linearly.** The cost per host-step grows only from 158 ns to 256 ns between 16
  and 2,048 hosts, roughly cache effects. A run of 60 steps at 2,048 hosts takes 31 ms.
- **Compilation is the steepest step.**
  - Compile time grows faster than the model: ×3.4 from 1,024 to 2,048 hosts.
  - Compiler memory grows about linearly: 2.4 GB at 87,000 variables. Memory, not time, limits size on
    this machine.
  - The excess comes from the program's dynamic-index fan-out: each access is expanded over the elements
    it can reach (the spine's port for a random destination leaf reaches NL of them). It also comes from
    the elaborator building the whole unrolled DAG, which the structured target does not emit.
  - The next compiler step is to skip that DAG for `--target native` (decision 56).
- **Sequential tests.**
  - Far from the threshold, SPRT decides in 12–16 runs at every size, against 1,203 for the fixed-sample
    test. Near the threshold it needs more (104 runs at 16 hosts).
  - The run count depends on the distance from the threshold, not on the model's size. At 2,048 hosts
    the whole test took 6.6 s.

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
  them, because rounds are nearly independent: the fabric drains between rounds, and P_T matches
  1 − (1 − p)^rounds.
- **For "within T" probabilities, the question itself changes with T.** P_T grows from 0.02 to 0.97,
  and the runs needed depend on how far P_T is from the threshold. The SPRT needed most runs (109) at
  T = 1,800, where P_T ≈ 0.44 sits next to the indifference region (0.45–0.55).
- **Horizon is not a scaling problem for simulation.** It is for exact methods, whose unrolled state
  space grows with T.

## Axis 3: a rarer bad event

A small fabric (2×8×2, B = 16, one round of 60 steps) and `loss` with THRESH = 6, where P ≈ 5·10⁻⁶.
Monte Carlo on the native simulator is compared with its RESTART and fixed-effort splitting
(`rare_event.py`, `results/rare_event.jsonl`).

- **Levels.** Expected success picks levels and factors from pilot runs (`splitting.py`).
- **Derived importance** (`--auto-importance`): min(odrops, 6), the query's progress.
- **Refined importance:** the derived one plus the aggregator port's backlog, min(odrops, 6)·17 +
  backlog(eg[0]).
- **Target.** A 95% interval with ± 10% relative half-width. Monte Carlo's time for that is extrapolated
  from its measured cost per run.

| importance | method | estimate | 95% interval | ± | runs | simulated steps | time | time for ± 10% (extrapolated) | vs Monte Carlo |
|---|---|---|---|---|---|---|---|---|---|
| — | Monte Carlo | 4.6·10⁻⁶ (32 hits) | [3.1, 6.5]·10⁻⁶ (Clopper–Pearson) | — | 7,000,000 | 420 M | 1,204 s | 10,600 s (62 M runs) | 1× |
| derived, 6 levels | RESTART, factors [133, 3, 5, 7, 12, 25] | 6.2·10⁻⁶ | [4.6, 7.8]·10⁻⁶ | 26% | 794,000 | 348 M | 904 s + 39 s pilot | 6,300 s | 1.7× |
| derived, 6 levels | fixed effort, 1,000 per level | 6.0·10⁻⁶ | [4.7, 7.2]·10⁻⁶ | 21% | 1,300 | 313 M | 916 s | 3,900 s | 2.7× |
| refined, 36 of 102 levels | RESTART | stopped: no batch of 2,000 runs finished in 2 h 50 min | | | | | | | — |
| refined, 36 of 102 levels | fixed effort, 1,000 per level | 6.9·10⁻⁶ | [4.2, 9.7]·10⁻⁶ | 39% | 800 | 375 M | 934 s + 19 s pilot | 14,500 s | 0.7× |

The splitting intervals are normal intervals from per-run estimates. The time for ± 10% scales each method's
measured time by (observed half-width / 10%)². The three splitting estimates agree with each other and with
Monte Carlo's interval. Monte Carlo's point estimate lies lower, with 32 hits. A shorter Monte Carlo check in
the second run (1 hit in 600,000) is consistent with both.

Two problems surfaced before these runs, and both are fixed.
- **Pilot averaging.** `expected_success` averaged each level's success fraction over all pilots,
  counting pilots that died below a level as 0 at that level. It now averages only over pilots that
  reached the level. It also takes `min_pilots`, because a single pilot, which is what stopping at the
  first one to reach the goal gives, mis-sizes the upper levels.
- **Uninformative importance.** Measured directly, fixed effort with levels 1–3 agrees with Monte Carlo:
  P(odrops ≥ 4) is 1.38·10⁻⁴ ± 1.5·10⁻⁵ against 1.42·10⁻⁴, and the per-level conditionals are 0.29,
  0.25 and 0.20 in both. But the entrance states of a level differ enormously in their prospects: a
  pilot that hits "hot" states (an incast still filling the queues) succeeds at about 40% per level,
  while most die by level 3. The derived importance counts drops and ignores the queues, so RESTART's
  retrials, cloned from one state, are strongly correlated.

**Reading.**
- **Splitting works here, but only modestly.** With the derived importance, fixed effort reaches a given
  precision about 2.7 times faster than Monte Carlo, and RESTART about 1.7 times. At P ≈ 6·10⁻⁶ that still
  means about an hour for ± 10% on a 16-host fabric. The rarity is real, but the levels are poor.
  - The pilot's level probabilities are 0.0075, 0.27, 0.23, 0.14, 0.085 and 0.039. Almost all of the
    rarity sits in the first drop: P(odrops ≥ 1) ≈ 0.0075 in one round.
  - Each further level cuts the probability by 4 to 25 times, but its retrials share the entrance state.
    Whether they succeed depends on the queues' contents, which the importance does not see.
  - The estimate's variance therefore comes from the spread over entrance states, and splitting cannot
    reduce that spread.
- **Refining the importance made things worse, and broke RESTART.** Adding the aggregator port's backlog
  gives 102 importance values. Expected success keeps the 36 levels whose rounded factor is at least 2.
  - **RESTART.** The factors multiply to 5.3·10¹³, against 1/P ≈ 1.7·10⁵.
    - Why it overshoots: the backlog rises and falls within a round, and each drop jumps the importance
      by 17. A trajectory therefore crosses many thresholds, often several times, and RESTART spawns
      retrials at every crossing.
    - No batch finished. The run was stopped after 2 h 50 min of CPU in its first batch of 2,000 runs,
      because the script's time budget is checked only between batches.
    - So RESTART's cost per run is unbounded unless the importance is close to monotone along
      trajectories. Expected success with integer factors does not guard against this.
  - **Fixed effort.** Its cost per level is bounded, so it ran. Its estimate agrees (6.9·10⁻⁶), but for
    equal time its variance is about 3.7 times that with the derived importance, and it is slower than Monte Carlo:
    36 levels of 1,000 trajectories each take time without adding information.
- **What this says about scale.** Splitting's gain depends on the importance function, not on the
  model's size. Both importance functions here are cheap to compute at any size. Neither captures what
  makes the event rare: a joint pattern of many responders' delays and ECMP choices filling one port.
  An informative importance function for incast would have to look ahead over the incast still in
  flight. That is a modelling task, which neither `--auto-importance` nor a queue-length heuristic
  performs.

## Which steps scale, and which do not

| step | scales here? | evidence |
|---|---|---|
| Modelling | yes | One parameterised Buffy program, 180 to 174,092 state variables. Arbitration and indices must be written so that every access reaches a few elements. |
| Compile (`--target native`) | to about 175k variables in 8 GB, paging at the top; superlinear | 51 s and 2.4 GB at 2,048 hosts. Two quadratic costs were removed (decision 56). The remaining excess is the unrolled DAG the structured target never uses. At 4,096 hosts (174,092 variables) it still compiles, but it takes 21 min (4.5 min of CPU) and 3.4 GB, and the machine was paging. A run there takes 57 ms, and the SPRT decides in 12 runs. |
| Build (clang) | yes | 31 s for 13 MB of C at 2,048 hosts. |
| Simulation | yes, linear in hosts × steps | 158–256 ns per host-step from 16 to 2,048 hosts, 50–70 µs per step at 256 hosts for any T up to 10⁴. Needed one runtime fix for steps with many draws. |
| Sequential tests (SPRT) | yes | Runs depend on the distance from the threshold, not on model size or horizon: 12–109 runs here. Rate estimates cost a constant number of simulated steps across horizons. |
| Rare events (splitting) | only with an informative importance function | 2.7× faster than Monte Carlo at P ≈ 6·10⁻⁶ with the derived importance (fixed effort; RESTART 1.7×). A refined, non-monotone importance made fixed effort slower than Monte Carlo and RESTART's effort unbounded (factor product 5·10¹³ against 1/P ≈ 2·10⁵): no batch finished in 2 h 50 min. |
| Exact conditioning (`--condition-on`) | no | The input process here has dozens to thousands of sources per step (four per host plus one per link). On-demand conditioning memoises h over the input states that runs reach. The responders' start delays alone give 11^M joint values at the first step: 2·10⁷ at 16 hosts (M = 7) and 9·10²³ at 32 hosts (M = 23). Conditioning on one source (e.g. the victim's arrivals) remains feasible; joint conditions over the incast do not. |
| Learning conditions over many sources | no (not attempted) | The learner (case studies B, C, F) searches conditions over the histories of one or two sources. Here the cause of collateral damage is a joint pattern over hundreds of responders' delays and ECMP choices. The hypothesis space grows exponentially in the sources, and so does the run count needed to certify a condition with small probability mass. |
| Exact model checking (Storm, mcsta) | no (not attempted, by policy) | The delay vector above alone bounds the reachable states from below by 2·10⁷ at 16 hosts and 9·10²³ at 32 hosts, before any queue contents; the state space also grows with the horizon. Exact checking is limited to the small reference examples of Buffy's test suite. |

## Conclusion

- **What scales.** Along every axis tried, the simulation-based pipeline scales to an industrial-size
  instance on a laptop: compile, build, simulate and sequentially test. At 2,048 hosts the fabric is a
  model of 87,052 state variables whose contention grows with size. It compiles in under a minute, a run
  costs 31 ms, and a sequential test decides in seconds. At 4,096 hosts (174,092 variables) everything
  after compilation is just as cheap. The compile itself, at 3.4 GB and 21 minutes, is at this
  machine's edge.
- **What the answers show.** Unlike Loom, the answers change with size: collateral damage from incast
  appears between 16 and 48 hosts and is nearly certain beyond. So the ability to analyse the large
  instance directly is what matters.
- **The limits are elsewhere.**
  - Compiler memory, from the unrolled DAG it still builds.
  - Rare events whose natural importance function, the query's progress, says little about the system's
    state.
  - Every exact technique: exact conditioning or learning over many sources, and exact model checking.
    These remain tools for small configurations and single sources.
- **A caveat on earlier results.** This study also found a sampling defect in the simulator that grows
  with the number of random sources per step. Earlier large-model results, in particular the Loom SPRT
  study, should be re-run with the fixed runtime before they are cited.
