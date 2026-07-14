# LCRL policy synthesis on the incast MDP — methodology

> New to this project? Read **`experiments/README.md`** first — setup, the
> pipeline, how to run each study, and a prioritised list of what to try next.
> This file is the detailed evidence behind those findings.

Can [LCRL](https://github.com/grockious/lcrl) (Logically-Constrained
Reinforcement Learning), applied to the **MDP** model
`models/example2_desync_short_bursts/incast_mdp.pm` and the LTL specification in
`incast_mdp.props`, recreate the result of the DTMC case study in that folder's
`NOTES.md`?

The DTMC case study computes `P[Q] = P[odrops>=THRESH]` — the probability of
receiver-facing incast loss — under **uniform-random** sender start times, and
reports `P[Q] = 0.54` at the least-favorable corner
`(M=16, WIN=96, SLEN=8, BUF=32, THRESH=8)`, rising to `1.0` at the most-severe
corner. The MDP replaces the uniform-random starts with **nondeterministic**
start timing (each waiting sender may *start now* or *wait*), and LCRL
synthesises a start-scheduling policy. This document records how we drive that
synthesis and how its output is compared with the case study.

## 1. Pipeline

```
incast_mdp.pm  ──load+instantiate consts──▶  PrismBlackBoxMDP   (black-box MDP, INDEX_LEVEL actions)
incast_mdp.props ──strip P[...]+PRISM→LTL──▶  LTL  ──OWL ltl2ldba──▶  HoaLDBA   (LCRL LDBA)
                     PrismBlackBoxMDP × HoaLDBA  ──▶  ShapedLCRL.train_ql  ──▶  policy (Q-table)
                                                  ──▶  Monte-Carlo evaluation on the MDP
```

All of the left/middle stages are the components committed earlier
(`src/netmdp/lcrl/`): `PrismBlackBoxMDP` exposes the LCRL MDP API over a StormPy
`INDEX_LEVEL` simulator; `PrismProperties` translates each PRISM property to LTL
and lifts its atoms; `owl.ltl_to_ldba` builds the LCRL LDBA via OWL. For the
incast property `P=? [ F ("done" & odrops>=THRESH) ]` the LTL is
`F (done & p1)` and the LDBA is deterministic with accepting set `[[2]]` and no
epsilon transitions.

## 2. Two corrections over the first attempt

### 2a. Dense, monotone reward (`ShapedLCRL`)

LCRL's stock reward is **sparse**: `1` only when the LDBA reaches its accepting
state (`done & odrops>=THRESH`), `0` otherwise. Over the incast MDP's long
per-episode horizon — `(MMAX+1) = 21` substages per slot × `HORIZON` slots
(≈ 5000 micro-steps at the case-study corner) — that single terminal signal
propagates too slowly for tabular Q-learning: in the first attempt `value@s0`
stalled and the learned greedy policy scored **0.00** in Monte-Carlo, versus an
exact `Pmax = 1.0`.

`ShapedLCRL` (`src/netmdp/lcrl/shaped.py`) replaces it with a reward that grows
**monotonically with `odrops`**, giving a gradient across the whole `0..THRESH`
range:

```
reward_t = sign · (odrops(s_t) − odrops(s_{t-1})) / THRESH
```

With `sign=+1` the undiscounted episode return equals `final_odrops / THRESH ∈
[0,1]`, so the policy **maximises** expected drops — the worst-case / adversarial
scheduler whose success probability estimates `Pmax[odrops>=THRESH]`. With
`sign=−1` it **minimises** drops — the loss-avoiding scheduler, estimating
`Pmin`. The `odrops` delta is read from `PrismBlackBoxMDP.full_state` /
`prev_full_state` (added for this purpose).

*Effect.* On the case-study corner `value@s0` rises `0 → 0.24 (ep200) → 0.92
(ep600) → ~0.98 (ep1000)` and the learned policy MC-evaluates to `Pmax`.

### 2b. Case-study constants

Runs use the paper-scale parameters `BUF=32, THRESH=8, M∈{16,20}, WIN=96,
SLEN=8` instead of toy values.

## 3. Tractability: state projection

Full-state tabular Q-learning is intractable at these constants (20 senders ×
`on/t`, 10 queues over `0..32`, etc.). The RL state is therefore **projected**
to `[slot, stage, odrops]` (≈ 5–6k product states visited). The reward still
uses the *full* `odrops` (projection affects only what the policy conditions on,
not the reward). This is enough to represent the relevant schedules (e.g.
"start every sender as early as possible" = synchronise). Exact model checking
is used only on small instances for ground truth (`exact_bracket.py`); it
explodes at the case-study corner, exactly as the DTMC study found.

## 4. What to compare — and what NOT to

**Compare the Monte-Carlo-evaluated policy, not `value@s0`.** On this long
horizon the *magnitude* of `value@s0` under-converges even after the greedy
policy is already optimal (small-instance check: `value@s0 = 0.48` while the
greedy policy MC-evaluates to `1.00`). So the quantity mapped to the case
study's `P[Q]` is `mc_evaluate(...)` of the learned policy: the empirical
`P[final odrops >= THRESH]`.

Three policies are MC-evaluated on the **same** MDP so the numbers are directly
comparable:

| policy | what it is | maps to |
|---|---|---|
| `lcrl_greedy` | the synthesised (max) policy | `Pmax[Q]` — worst-case scheduler |
| `uniform_hazard` | start w.p. `1/(WIN+1−slot)`, else wait | **reproduces the DTMC** `P[Q]` |
| `always_start` | always choose *start* | full-synchronisation baseline |

The `uniform_hazard` policy replays the DTMC's per-slot hazard on the MDP, so it
is the anchor: if it reproduces the case study's `P[Q]`, the MDP-under-uniform
*is* the DTMC, and any gap up to `Pmax` (or down to `Pmin`) is the value the
nondeterminism adds.

## 5. Results

**Ground truth (exact, small instances — `exact_bracket.py`).**
`(M=4, WIN∈{1,2}, small BUF/THRESH)`: `Pmax = 1.0`, `Pmin = 0.0`. The shaped
policy recovers it: greedy MC `P[Q] = 1.000` (sparse reward gave `0.00`).

**DTMC reference (`dtmc_reference.py`, `incast.pm`, uniform start).**

| corner | `P[Q]` (DTMC) |
|---|---|
| `M=16, WIN=96, SLEN=8` | **0.507** (≈ the NOTES `0.54`) |
| `M=20, WIN=96, SLEN=8` | **1.000** |

**MDP + LCRL (`run_synthesis.py`), MC `N=300`, `P[Q]` | mean_odrops.**

*M=16 — the discriminating corner:*

| policy | `P[Q]` | mean_odrops |
|---|---|---|
| `lcrl_greedy` (Pmax) | **1.000** | 8.00 |
| `uniform_hazard` (=DTMC) | **0.533** | 5.52 |
| `always_start` | 1.000 | 8.00 |
| DTMC reference | 0.507 | — |

*M=20 — saturated:*

| policy | `P[Q]` | mean_odrops |
|---|---|---|
| `lcrl_greedy` (Pmax) | 1.000 | 8.00 |
| `uniform_hazard` (=DTMC) | 1.000 | 8.00 |
| `always_start` | 1.000 | 8.00 |
| DTMC reference | 1.000 | — |

## 6. Interpretation

- **The `uniform_hazard` policy reproduces the DTMC** (`0.533 ≈ 0.54` at M=16;
  `1.0` at M=20). This validates that the MDP under a uniform start policy is the
  case-study DTMC — the two models agree where they should.
- **LCRL recovers `Pmax = 1.0`**: an adversarial scheduler synchronises the
  senders and forces the loss with certainty, regardless of the wide `WIN=96`.
- The case study's single uniform number is therefore **one point inside the
  schedule bracket `[Pmin, Pmax]`**. At **M=16** the bracket is non-trivial —
  `Pmin ≤ 0.54 (uniform) ≤ 1.0 (Pmax)` — so the nondeterminism genuinely adds
  information (this is the "worst-case bracket without committing to the uniform
  distribution" that `HANDOFF.md` proposed as the MDP next step). At **M=20** the
  corner is *saturated*: uniform, worst-case, and always-start all give `1.0`, so
  LCRL recreates the result trivially but the bracket collapses.
- **`Pmin` and the forced-start model.** In `incast_mdp.pm` the loss-avoiding
  direction (`--direction min`) hits `Pmin ≈ 0` *degenerately*: a waiting sender
  may wait through the whole window and then (once `slot > WIN`) never start, so
  a scheduler avoids all drops by simply **not sending** (`run_synthesis.py
  --direction min` prints `mean_senders_started` -- ≈ 0 flags this). To make
  `Pmin` physical, **`incast_mdp_Pmin.pm`** keeps the per-slot start-vs-wait
  choice but enables the *wait* command only while `slot < WIN`; at `slot = WIN`
  wait is disabled, so a still-idle sender is **forced to start**. Every
  in-fan-out sender therefore starts by the window's end, the nondeterminism is
  retained where it matters (`slot < WIN`), and the decisions stay interleaved
  with per-slot service (no separate phase). Exact checking on small instances
  confirms it is well-formed: `Pmax = 1.0`, `Pmin = 0.0`, `max_actions = 2`,
  every rollout starts all `M` senders, and -- because never-started states
  become unreachable -- the state space is *smaller* than `incast_mdp.pm`. So at
  small fan-in incast loss *is* avoidable by spreading starts; whether
  `Pmin > 0` (loss unavoidable) at the case-study fan-in is the open question
  this model poses.
- **Why RL does not yet synthesise `Pmin`.** Tabular LCRL-min returns a greedy
  policy with `P[Q] = 1.0` on `incast_mdp_Pmin.pm`, despite exact `Pmin = 0`.
  Two regimes were investigated and they rule out the "obvious" causes:
  - **Tiny instance** (`M=4, THRESH=1`, full state, exact `Pmin=0`): the
    incast-free schedule is *rare* (random policy loses with `P[Q]=0.958`, only
    ~4% avoid loss), and with optimistic initialisation `value@s0≈0` is a *false*
    optimum -- for a minimisation, unexplored states look perfect, so the greedy
    walks into unexplored territory (defaulting to `start`) and drops. Neither
    **double Q-learning**, **smaller α**, nor **pessimistic init** (which makes
    `value@s0=−1` *honest*) moves the greedy off `P[Q]=1.0`: **overestimation is
    not the cause**.
  - **Reasonable constants** (`M=16, WIN=96, SLEN=8, BUF=32, THRESH=8`; state
    projected): LCRL-min gives `P[Q]=1.0`, *worse* than the uniform baseline's
    `0.53`, for **every** projection tried -- `[slot,stage,odrops]`,
    `+qo_bucketed`, `+qo_bucketed,n_active_bucketed`. The identical `1.0`
    (`mean_odrops=8`, exactly always-start) reveals the mechanism: the
    **deterministic greedy collapses to a synchronising extreme**. In the
    forced-start model there are two ways to synchronise, both giving 8 drops --
    *start everything ASAP* (coincide near slot 0) or *wait everything* (all hit
    the `slot=WIN` deadline and are forced to start together). A deterministic
    tabular policy makes ~one decision per `(slot, congestion)` state and drifts
    to a pole; it cannot **stagger** senders across the window. Uniform's `0.53`
    comes precisely from **stochastic** staggering, which a value-based greedy
    (deterministic) cannot reproduce.
  - So richer **state projection is necessary but not sufficient** (the congestion
    features make a spread policy *representable* but the terminal-only reward
    never *teaches* it), and the blocker is that staggering is not learnable from
    a terminal reward. **`Pmax` trains cleanly** (`P[Q]=1.0`), so the model is
    RL-trainable; only the stagger-requiring `Pmin` direction fails.

  Per-slot / per-substage congestion **reward shaping** was tried (penalise `qo`
  per slot; penalise `n_active` per substage, linear and convex), across weights
  and with pessimistic Q-initialisation. **None moved `P[Q]` off `1.0`.** Worse,
  with the minimisation framing the shaping is *counter-productive*: it drives
  explored (congested) states more negative than the optimistic `Q_init=0`, so
  the greedy flees to unexplored states even harder (`value@s0` fell to `−29`
  while `P[Q]` stayed `1.0`). State projections may include **derived congestion
  features** (`PrismBlackBoxMDP` accepts callables in `state_variables`;
  `run_synthesis.py --state-vars` exposes `qo_bucketed`, `n_active_bucketed`,
  `Ftot`), but no projection helped.

- **The real cause was the *framing*, not the learner: `Pmin` is LTL
  *maximisation* of the complement.** All of the above minimised a `−Δodrops`
  reward. That is self-sabotaging: for a minimisation the returns lie in
  `[−1, 0]`, so the default `Q_init=0` is the *best* possible value — unexplored
  states look optimal, so the greedy `argmax` flees into unexplored territory
  (defaulting to `start`) and synchronises; every congestion penalty makes
  explored states look worse and *strengthens* the flight. LCRL is not built to
  minimise a reward — it **maximises the probability of satisfying an LTL
  property**. The native route to `Pmin` is the complement:

      Pmin[F(done & odrops>=THRESH)] = 1 − Pmax[F(done & odrops<THRESH)]

  i.e. run LCRL on `φ_safe = F("done" & odrops<THRESH)` with its own
  `+1`-at-the-accepting-state reward. Now returns lie in `[0, 1]`, so `Q_init=0`
  is the *worst* value — unexplored looks bad and the greedy prefers *proven-safe*
  paths. **The optimistic-init pathology does not arise.** Two clarifications:
  - **A deterministic optimum exists.** For MDPs and ω-regular objectives there is
    always an optimal *deterministic* (memoryless-over-the-product) policy; exact
    checking finds a deterministic scheduler achieving `Pmin=0` at small scale. So
    the uniform-beats-learned gap (0.53 vs 1.0) is a *learning* failure, not proof
    that a stochastic policy is required.
  - **What is genuinely general** (not LCRL-specific): exploration of the safe
    trajectory (regime-dependent — rare ~4% at `THRESH=1`, common ~47% at the
    `THRESH=8` corner, where native LCRL on `φ_safe` should work) and state
    abstraction at scale (a lossy projection may not represent the optimum). These
    are ordinary RL costs, and exactly where a *learned, generalising* policy is
    meant to beat exact/SMC, which cannot scale.

  **Empirically, at M=16, `φ_safe`-maximisation still returns `P[Q]=1.0`** across
  configs (pure native; native+drop-shaping; +`n_active` projection) — so the
  framing correction is **necessary but not sufficient**, and it is honest to say
  the earlier "this is the fix" was premature. The `value@s0` values say why:
  *pure native* gives `value@s0 = 0.000` — the `+1`-at-`done` LTL reward is too
  **sparse** to propagate over the ~4872-step horizon (the very problem the dense
  reward was introduced to solve for `Pmax`); adding drop-shaping propagates the
  value (`-0.06 … -0.9`) but the greedy still collapses to the synchronising pole
  (the **state-abstraction / deterministic-staggering** limits at reasonable
  constants remain). So removing the optimistic-init pathology exposes the *other*
  two general RL costs (sparse-reward horizon, and lossy abstraction of a
  stochastically-staggered optimum), which are the binding constraints for this
  `Pmin`. Net: the `Pmin` difficulty is a **combination** — a framing error (now
  corrected) plus ordinary RL exploration/horizon/abstraction costs — not a
  fundamental LCRL limitation, but not solved here either. For the `Pmin`
  *value*, exact/SMC remains the reliable route where it is tractable. Note the
  **maximisation** direction (worst-case), where LCRL is strong, is exercised
  cleanly in `models/example3_fqcodel/` (worst-case FQ-CoDel starvation).

**Bottom line.** LCRL on the MDP recreates the case-study `P[Q]` where the
scheduler is forced (it recovers `Pmax = 1.0`, and `uniform_hazard` reproduces
the DTMC value exactly), and reframes the single uniform probability as a
schedule bracket. The genuinely new question the MDP could answer — *is incast
loss avoidable by scheduling?* — needs the "all senders must start" constraint
before `Pmin` is physically meaningful.

## 7. Reproducing

Run from the repo root with the venv that has `stormpy` + `lcrl`; OWL is
auto-located (`owl-*/bin/owl`) or set `$OWL_PATH`.

```bash
# DTMC reference values (uniform start):
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/dtmc_reference.py

# exact Pmax/Pmin ground truth on small instances:
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/exact_bracket.py

# MDP + LCRL synthesis, discriminating corner, worst-case scheduler (Pmax):
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py \
    --M 16 --WIN 96 --SLEN 8 --BUF 32 --THRESH 8 --direction max

# saturated corner:
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py --M 20

# loss-avoiding scheduler (Pmin) on the forced-start model (all senders send):
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py \
    --model incast_mdp_Pmin --M 16 --direction min
```

Runtime is a few minutes per corner (≈1200 episodes × ~5000 micro-steps, then
3 × 300 MC rollouts). Results are stochastic; `P[Q]` is a Monte-Carlo estimate
(±~0.03 at `N=300`), and `value@s0` is not the comparison quantity (§4).

## 8. Files

| file | role |
|---|---|
| `src/netmdp/lcrl/shaped.py` | `ShapedLCRL` (dense reward), `mc_evaluate`, `greedy_action`, `uniform_hazard_policy` |
| `run_synthesis.py` | train + MC-evaluate a corner (`--model`, `--direction max`/`min`) |
| `dtmc_reference.py` | DTMC `P[Q]` at the corners (uniform start) |
| `exact_bracket.py` | exact `Pmax`/`Pmin` on small instances, both models (StormPy) |
| `models/.../incast_mdp_Pmin.pm` `.props` | forced-start MDP (wait only while `slot<WIN`) for a physical `Pmin` |
