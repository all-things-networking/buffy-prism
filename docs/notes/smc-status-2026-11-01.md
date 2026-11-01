# SMC status: modes replication, sequential tests, scheduler learning, Momba (2026-11-01)

Companion to [jani-vs-prism-compilation-target.md](jani-vs-prism-compilation-target.md). Everything here is on branch
`claude/netmdp-chernoff-hoeffding-6cb4b1`. Unless stated otherwise, the numbers come from runs in this branch.

## 1. STAT 535C replication with modes

- Model: `tests/models/fqcodel_5i_mdp_535c.pm` (copy of the course model). `tests/modes/make_course_jani.py` writes
  the Weibull-traffic DTMC (`fqcodel_5i_weibull_dtmc_535c.{pm,jani}`), the MDP (`fqcodel_5i_mdp_535c.jani`) and an MDP
  with a step counter (`fqcodel_5i_mdp_535c_steps.jani`).
- Runner: `tests/modes/run_course_experiments.py` (10 seeds × {base SPRT, base CR, RESTART/CR, weighted fixed effort
  (8)/CR}, expected-success levels, importance `iq5_deqs_bl`). Results: `tests/modes/results/course_replication.json`.
- The course numbers replicate. SPRT accepted H+ in all 30 runs. The course-CR run counts computed from modes'
  per-run variances match the course runs (RESTART Exp 3: 23.9k vs 24.4k).
- modes costs about 45 µs per 154-step DTMC run, roughly 40–300× faster per run than the stormpy samplers.
- Work-normalised relative variance (Var(p̂)/p² × time):
  - At p ≈ 4e-4, RESTART is 0.059 against 0.36 for base SMC, a 6× gain; weighted fixed effort is 0.09.
  - At p ≈ 0.013, base SMC wins.
  - The slides' a_N = R_err²·N counts N twice.
- modes' `ChowRobbins` is the original 1965 rule n ≥ (z/ε)²(σ̂² + 1/n). The absolute 1/n term dominates for rare
  events: weighted fixed effort in Exp 3 needs 36k runs against about 6k for the course CR.

### Reference values and the `==` vs `>` discrepancy

Reference values from modes, a simulator independent of PRISM (2M base runs; RESTART at ±2 % relative width for
k ≥ 8, 95 % CIs):

| k | P(deqs > k within 154 steps) | P(deqs = k+1 at step 154) = P(>k) − P(>k+1) |
|---|---|---|
| 2 | 0.7146 [0.7140, 0.7152] | 0.6693 (P(>3) = 0.04532) |
| 4 | 0.01294 [0.01279, 0.01310] | 0.00634 (P(>5) = 0.00660) |
| 8 | 4.09e-4 [4.01e-4, 4.17e-4] | 3.07e-4 (P(>9) = 1.02e-4) |

- The course base samplers (`BaseSymbolicSMCSampler.sample`) test `iq5_deqs_bl == goal_deq` at step 154, i.e. the
  right column. The splitting samplers and the PRISM reference values measure the left column.
- Confirmed by the course CR sample sizes, z²p(1−p)/ε² with the right-column p: 23,960 / 67,770 / 332k against the
  course's 23,921 / 66,806 / 355,744.
- Consequence: the course Exp 2 base-SMC rows tested 0.0063 < θ = 0.011, which is why SPRT accepted H−. Exp 3's
  "p ≈ 0.0003" is the same quantity.
- Exact (explicit or symbolic) model checking is out of scope at this model size; reference values are statistical.

## 2. Sequential tests (base SMC, Bernoulli paths)

`tests/sequential_test_comparison.py` replays identical paths through every test. Its vectorised runners are
checked against the classes.

- **Naive early stopping** (re-checking the fixed-n CI every sample) is invalid: 37–88 % wrong acceptances at p = θ.
- **`ChowRobbins(mode="anytime")`**, now the default, uses an asymptotic confidence sequence: Robbins' normal mixture
  (Waudby-Smith et al., AoS 2024), an exact all-zero rule for H−, and a small-sample variance correction for the H−
  check. `mode="fixed_width"` is the course version; `tests/cr_test_runner.py` pins it.
  - At the true p it uses about 10k / 36k / 75k samples (θ = 0.7 / 0.011 / 1.5e-4), against 22k / 137k / 442k for
    fixed-width CR; power is ≥ 0.975 at θ ± ζ.
  - Its guarantee is asymptotic. Observed wrong-acceptance rates at p = θ (600 paths): 2.3 %/4.5 %, 0.7 %/6.5 %,
    0 %/5.2 % (H+/H−). Fixed-width CR reaches 13.5 % at θ = 1.5e-4.
- **SPRT** remains the most sample-efficient (2.3k / 9.3k / 8k at the true p). Wald–Wolfowitz optimality leaves about
  30 % room at most.
- **Adaptive Chernoff–Hoeffding** (`adaptive_chernoff_hoeffding.py`) is the only test here that is exactly valid at
  every n. It needs 19k / 62k / 49k samples, beating CR anytime at the rarest θ, but it cannot credit splitting's
  variance reduction.
- Not yet done: CR anytime on splitting samples (modes `--cdf` exports per-run values for an offline replay).

## 3. Adversarial traffic: modes scheduler learning on the MDP

The MDP has no probabilistic branching, so Pmax ∈ {0, 1}. The Weibull DTMC shows P > 0, so Pmax = 1 for every k.

| Goal | uniform resolution | LSS (10k schedulers) | Q-learning, memoryless | Q-learning + step counter |
|---|---|---|---|---|
| > 2 | – | 1 | 0.0001 (learned value 0.98) | 1 |
| > 4 | – | 0 | 0.9999 | 0.9999 |
| > 8 | 0 (200k runs) | 0 | 0 | 0 (50k episodes, never rewarded) |

- modes' LSS and Q-learning only consider memoryless schedulers, so step-bounded goals need a step counter in the
  state (`add_step_counter` in `make_course_jani.py`: one JANI variable plus one assignment per edge).
- Without it, greedy policies get stuck in cycles: learned value 0.98, evaluated 0.0001.
- The 4× goal fails because the reward is sparse. That is the case for our own scheduler class and RL loop with
  potential-based shaping from the splitting importance function, or with witnesses seeded from the Weibull DTMC.
- Not yet compared with LCRL.

## 4. Momba 0.6.12 (tried in a scratch venv; not recommended)

- **Silent semantic bug:** `momba/engine/translator.py::_extract_constraints` translates `x ≠ c` into
  `x < c ∧ x > c`, so those guards are never enabled. Verified in the source. Every FQ-CoDel run deadlocked until
  `≠` was rewritten as `¬(=)`.
- The bare-expression `imp` property is rejected (`InvalidJANIError`).
- With both fixes, estimates match modes (P(>2) ≈ 0.716).
- Speed: 24–31 µs/step through private Rust handles, about 70–240 µs/step through the public API, against about
  45 µs per whole run in modes.
- No value-based state equality, no pickling, no constructing a state from values.
- The gym wrapper uses the old gym API, drops step bounds, and mis-resolves labelled actions.
- No checking without Storm or modes, and no LTL beyond syntax. Last release August 2024.

## 5. Native simulation engine, schedulers and learning (later the same day)

**Engine: `src/netmdp/sim/jani_native.py` (JANI → C → ctypes).**
- Compiles a single-automaton JANI MDP or DTMC into a C step function, cached in `~/.cache/netmdp-jani`.
- Supported subset: bounded int and bool variables, constants, `+ - * / % min max abs floor ceil`, comparisons,
  `∧ ∨ ¬ ⇒`, `ite`, and probabilistic edges with simultaneous assignments. Anything else raises `JaniUnsupported`.
  Assignment indices and multi-automaton synchronisation are not supported yet.
- A state is an int32 vector, so anchors are copies and states hash by value.
- Speed: 24 ns/step, about 3.3 µs per 154-step run in its batch path (`simulate`, `simulate_scores`). That is about
  13× faster than modes and 1000× faster per step than stormpy. Through the Python `Simulator` interface it costs
  about 9 µs/step.
- Validated:
  - identical choice lists and all 19 variables against stormpy's PRISM simulator over 3,080 random steps, with
    save/restore anchors;
  - P(>2) and P(>4) match the modes reference values.

**Interfaces.**
- `src/netmdp/sim/simulator.py`: the `Simulator` ABC (choices by action name, `step`, `save`/`restore`) with two
  backends, `NativeJaniSimulator` and `StormpyPrismSimulator` (reference; Storm compressed-state anchors, no replay).
- `src/netmdp/sim/scheduler.py`: `Scheduler` (state, choices, memory → distribution), plus `UniformScheduler`,
  `ActionWeightScheduler`, `arrival_count_scheduler(WEIBULL_TRAFFIC)`, `PolicyScheduler`, and `Rollout`, whose
  anchors include the scheduler memory.
- `src/netmdp/sim/export.py::induced_dtmc_jani`: writes the DTMC a state-independent scheduler induces on a JANI
  MDP, for modes. Validated: the Weibull export reproduces the hand-built DTMC (60 → 40 edges) and its probabilities.

**Learning.** `tests/scheduler_learning_experiment.py`; results in
`tests/modes/results/scheduler_learning.json`.
- `src/netmdp/learn/shaped_qlearning.py`: tabular Q-learning, step-aware keys, reverse-order episode updates.
  - It learns a witness for the 4× goal (greedy policy reaches it at step 126, P = 1) in 20k episodes (about 35 s).
    modes' Q-learning failed there.
  - Without reverse-order updates, or with memoryless keys, it does not retain the success.
  - Potential shaping with Φ = `iq5_deqs_bl`/(k+1) made learning worse in every configuration. Shaping in a
    zero-initialised table equals Q-initialisation with Φ (Wiewiora 2003), which changed exploration for the
    worse here. It is off by default.
- `src/netmdp/learn/cross_entropy.py`: rare-event cross-entropy method for an adversarial i.i.d. per-queue arrival
  distribution (2 s with the native batch path).
  - It learns IQ5 ∈ {0, 1} packets (0.54/0.46), with IQ1–4 near Weibull. That is the steady sparse flow that
    triggers the FQ-CoDel bug.
  - P(4× fair share) under it: modes RESTART 0.01161 [0.01138, 0.01184], native MC 0.01179. Under Weibull:
    4.09e-4 (modes) and 3.90e-4 (native), so the learned distribution is about 28× more adversarial.

**Item-3 follow-ups.**
- `BaseSymbolicSMCSampler` now counts `iq5_deqs_bl >= goal_deq`, i.e. P(> k), not `==`.
- `FixedEffortSMCSampler` keeps duplicate entrance states, since dropping them biased the estimator.
- `tests/modes/cr_on_splitting.py` runs the tests on i.i.d. draws from the per-run RESTART distribution exported
  by modes (`--cdf`), at θ = 1.5e-4, ζ = 1e-4, p ≈ 4.1e-4 (200 paths each):
  - RESTART + CR anytime: P(H+) = 1.000, 7.7k runs, about 3.5 s;
  - RESTART + CR fixed-width: P(H+) = 0.885, 20.7k runs (heavy-tailed RESTART estimates, sd/mean 11.5);
  - base SMC + SPRT: P(H+) = 1.000, 8.0k runs, about 1.2 s.

  Splitting does not yet beat SPRT for this test; it needs rarer events or cheaper splitting runs.

## 6. Native splitting, and splitting vs SPRT (overnight, unattended)

**Native splitting** (`JaniModel.restart` / `fixed_effort` in the generated C; `src/netmdp/sim/splitting.py` for
expected-success levels and `NativeSplittingSampler`):
- RESTART splits on every up-crossing (re-crossings included), once per crossed threshold, and kills retrials below
  their creation level; a goal at level ℓ counts 1/∏_{i<ℓ} R_i.
- Fixed effort resamples entrance states uniformly with replacement, keeping multiplicity.
- Validated against the modes references:
  - P(>4): RESTART 0.0128 ± 0.0005, fixed effort 0.0128 ± 0.0002, against 0.0129 [0.0128, 0.0131];
  - P(>8): RESTART 4.24e-4 ± 0.28e-4, fixed effort 4.15e-4 ± 0.11e-4, against 4.09e-4 [4.01, 4.17]e-4.
- Speed: a RESTART run costs 4–7 µs natively, against 449 µs in modes.
- At P(>8) RESTART's work-normalised relative variance is 7.5× lower than base SMC's.

**Splitting vs SPRT** at the same relative hypothesis as Exp 3 (θ = p/2.73, ζ = 2θ/3, α = β = 0.05).
`tests/native_splitting_experiment.py` and `tests/native_crossover_experiment.py`; results in
`tests/modes/results/native_{splitting,crossover}.json`. 20 reps each, all decisions correct.

| goal | p | base SMC + SPRT | native RESTART + CR anytime |
|---|---|---|---|
| > 8 | 4.0e-4 | 9.0k runs, 37 ms | 9.4k runs, 76 ms |
| > 9 | 1.0e-4 | 27.7k runs, 111 ms | 21.4k runs, 155 ms |
| > 10 | 1.7e-5 | 169k runs, 681 ms | 75k runs, **582 ms** |
| > 11 | 1.7e-6 | 2.19M runs, 10.7 s | 285k runs, **4.8 s** |

Splitting with an anytime test overtakes SPRT below about p ≈ 2e-5, and the gap grows as p shrinks. Weighted fixed
effort uses the fewest runs (4k at > 8), but each run costs about 70 µs, so it loses on time here.

**Compiler extensions for the Buffy emitter** (requested by the Buffy-to-JANI session):
- assignment `index` levels;
- transient variables, plus location transient-values, so Storm-exported PRISM labels can be used as goals;
- multi-automaton networks with synchronisation vectors.

Validated exhaustively against Storm's explicit model on `tests/models/sync_toy.pm` (4 modules, 3-way sync; all 640
states) and the die MDP: `tests/test_jani_native.py`. FQ-CoDel estimates are bit-identical with a fixed seed.

**Smoke tests of the fixed stormpy samplers** (course model): the base sampler now gives P(>2) = 0.713 ± 0.023
against the reference 0.7146, at 16 ms/run (native: 3.6 µs). The fixed-effort sampler runs and its estimate is
consistent with the reference.

## 7. Buffy emitter output on the native simulator

The emitted models (FQ, `experiments/buffy_jani/models/` in the goofy-kapitsa worktree, buffy@e45184e) are checked by
`tests/buffy_jani_check.py`; 1M runs per property.
- **Agreement:** every DTMC property agrees with the Buffy session's modes references within about 2 standard
  errors, and native sync and staged layouts agree with each other to 3–4 digits. Examples:
  - P0 = 0.6: starve 0.01189 (modes 0.01191), cond_a 0.8675 (0.8670);
  - P0 = 0.2: starve 3.5e-4 (modes 3.5–4.4e-4, direct Python MC 3.25e-4).
- **MDP with uniform choices** reproduces the uniform DTMC in both layouts.
- **Code-size fix:** generating code per joint destination produced 128 MB of C for the sync layout (5 traffic
  automata × 5 outcomes, each copying the 42-level step block). Code is now generated once per automaton edge,
  network transitions call their parts, and joint outcomes are mixed-radix indices sampled part by part. The C is
  now 65 KB and compiles in 0.6 s.
- **Cost per run:**
  - DTMC sync: 6.5 µs per 14-step run (modes: about 130 µs).
  - Staged: 5.7 µs per 84-step run.
  - MDP sync: 3.5 µs/step, because all 3125 joint choices are enabled in every state.
  - MDP staged: 63 ns/step.

  Recommendation (sent to the Buffy session): use per-source choice layouts (staged) for MDPs, simulation and RL.

  **Decided (user, 2026-11-01): adopt the per-source-choice-then-sync MDP layout.**
  - Each traffic automaton makes its own arrival choice, in a fixed order, into a persistent bounded variable; then one `tick` sync runs the step block.
  - It becomes the default for MDPs whose sync layout would exceed 64 joint choices. DTMC layouts are unchanged, and `--staged` stays recommended for RL.
  - Step bounds then count choice steps too. The Buffy session is asked to scale them by (sources + 1) or bound by a time counter.
  - Implemented as `buffyc-mc --layout choose` (Buffy `features` d7ff54e). It is the `--layout auto` default above 64 joint choices. Step bounds are scaled by (K+1) and goals are evaluated at `turn = 0`.
  - **Native validation** (`tests/buffy_jani_check.py`, 1M runs, uniform over enabled edges). Mixed model: queues 0–3 nondet, queue 4 at P0.
    - P0=0.6 starve: choose 0.01190 ± 0.00021, staged 0.01207 ± 0.00021.
      - modes, 100k runs: 0.01245, 99% CI [0.01177, 0.01316].
      - DTMC references: 0.0119–0.0120.
    - P0=0.2 starve: native 3.37e-4 ± 3.6e-5; modes 4.2e-4 (about ±1.7e-4).
    - The remaining properties agree within modes' error. cond_a and early at P0=0.2 sit about 2σ below native on one shared modes seed. The native value matches the earlier all-nondet uniform runs (0.99841 / 0.99809).
  - **Cost per time step:**
    - choose 5 × 95 ns ≈ 0.48 µs; staged 6 × 73 ns ≈ 0.44 µs; the old sync MDP 3.5 µs.
    - choose compiles in 0.6 s, against 84 s for the sync MDP.

## Design decisions to review (made unattended)

1. **Simulation engine: our own JANI → C compiler**, in C rather than Rust (clang already installed, no
   build/binding toolchain) and loaded with ctypes. stormpy stays as the reference backend. modes (closed) is used
   for cross-validation and for estimating under exported schedulers.
2. **Native batch paths** (`simulate`, `simulate_scores`, `restart`, `fixed_effort`) accept only memoryless,
   state-independent schedulers given as per-action weights. State-dependent and learned policies go through the
   Python `Simulator`/`Rollout` path (about 9 µs/step).
3. **Q-learning updates run in reverse order** after each episode; the step count is part of the key by default;
   shaping is available but off by default (it hurt).
4. **Cross-entropy** learns one arrival distribution per input queue (i.i.d. over time), elite quantile ρ = 0.05,
   smoothing 0.7. It is a distribution-learning method, not RL, and needs no reward design.
5. **Chow-Robbins default is `mode="anytime"`**, with `mode="fixed_width"` kept for the course runners.
   `min_nonzero` = 10 by default (30 helps at θ = 1.5e-4).
6. **Splitting levels:** expected success with pilot effort 256. Importance is `min(iq5_deqs_bl, k+1)`, matching
   the course `ImportanceFQCodel`.
7. **Native fixed effort resamples entrance states uniformly with replacement**, the textbook unbiased version.
   The course sampler cycles round-robin.
8. **JANI composition follows the spec.** For a single automaton, an action in no sync vector still fires alone,
   for compatibility with Storm's export. For networks, such actions never fire, with a warning.
9. **Exact model checking is never used on the network models.** Storm explicit checks are used only for toy-model
   compiler tests.
10. **Synchronised transitions sample their participants' outcomes independently**, one inverse-CDF draw per
    participant from a single uniform rescaled within the chosen interval. This is exact, and keeps the batch
    simulators' single-uniform-per-step interface.
11. **For the Buffy emitter's output, cross-check against modes, not Storm**, because of the Storm bug the Buffy
    session found for multi-level transients across synchronised edges. Storm stays the oracle for the toy-model
    equivalence tests, which have no transients.

## Next steps

1. Native splitting and learning on the Buffy emitter's models (staged MDP for RL; `imp` = `fq_deqs_bl`).
2. Bounded-LTL monitors as extra JANI automata or indexed observer assignments. The compiler now supports both.
3. Compare the step-aware Q-learner and cross-entropy against LCRL on the same MDP and monitor.
4. A native splitting path for state-dependent schedulers (for example a tabular policy compiled into C), if
   learned policies need rare-event evaluation without exporting to modes.
