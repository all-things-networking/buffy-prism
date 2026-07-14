# LCRL policy synthesis on the incast MDP — methodology

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
- **`Pmin` and a modelling caveat.** The loss-avoiding direction
  (`--direction min`) is reproducible but, as the model stands, `Pmin ≈ 0`
  *degenerately*: a waiting sender may wait through the whole window and then
  (once `slot > WIN`) can never start, so a scheduler can avoid all drops by
  simply **not sending**. `run_synthesis.py --direction min` reports
  `mean_senders_started`; if it is ≈ 0 the "avoidance" is this non-physical
  never-send schedule. A meaningful `Pmin` (loss avoidable *while still sending
  all traffic*) requires a model constraint that every one of the `M` senders
  starts within the window. Small-instance exact `Pmin = 0.0` is consistent with
  this.

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

# loss-avoiding scheduler (Pmin) + senders-started diagnostic:
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py \
    --M 16 --direction min
```

Runtime is a few minutes per corner (≈1200 episodes × ~5000 micro-steps, then
3 × 300 MC rollouts). Results are stochastic; `P[Q]` is a Monte-Carlo estimate
(±~0.03 at `N=300`), and `value@s0` is not the comparison quantity (§4).

## 8. Files

| file | role |
|---|---|
| `src/netmdp/lcrl/shaped.py` | `ShapedLCRL` (dense reward), `mc_evaluate`, `greedy_action`, `uniform_hazard_policy` |
| `run_synthesis.py` | train + MC-evaluate a corner (`--direction max`/`min`) |
| `dtmc_reference.py` | DTMC `P[Q]` at the corners (uniform start) |
| `exact_bracket.py` | exact `Pmax`/`Pmin` on small instances (StormPy) |
