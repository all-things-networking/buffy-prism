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

## Next steps

1. The scheduler class (state, memory → distribution over named actions; frozen during estimation, with memory in
   splitting anchors) and an RL loop with importance-function shaping. Candidate simulators: stormpy with saved-state
   anchors (`restart(bitvector)`, about 480× faster than prefix replay), or a generated native step function.
   Momba is out.
2. Run CR anytime on splitting runs exported by modes.
3. Fix the course base samplers' `==` check, or document it, before reusing their numbers.
4. Compare modes Q-learning against LCRL on the same MDP with a bounded-LTL monitor.
