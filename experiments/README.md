# LCRL policy synthesis over PRISM MDPs — a newcomer's guide

This directory drives [LCRL](https://github.com/grockious/lcrl) (Logically-
Constrained RL) over PRISM MDP models to **synthesise a policy** that maximises
the probability of an LTL property, and to **read that policy back as an
explanation** (a worst-case traffic pattern, a schedule, etc.). It is the RL
counterpart to the SMC/model-checking studies in `models/`.

Start here if you are picking this up. Read this file, then
`incast_mdp_lcrl/METHODOLOGY.md` (the detailed findings), then the per-study
`models/*/NOTES.md`.

## 1. Setup
- Python venv with `stormpy` (1.13) and `lcrl` is at the **repo root** `.venv`
  (NOT inside git worktrees). Use `.venv/bin/python`.
- Run everything **from the repo root** with `PYTHONPATH=.` (the code uses
  absolute `from src.netmdp...` imports and there is no `src/__init__.py`):
  ```
  PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py --help
  ```
- **OWL** (LTL→LDBA) is auto-located: `find_owl()` looks for `owl-*/bin/owl` in
  ancestor dirs, or set `$OWL_PATH`. The bundled build is `owl-macos-amd64-21.0/`
  at the repo root. Use the native `bin/owl`, not the jars.

## 2. The pipeline (what happens under the hood)
```
model.pm  ─load_prism_program→  PrismBlackBoxMDP   (black-box MDP; INDEX_LEVEL actions)
model.props ─PrismProperties→   LTL  ─owl ltl2ldba→  HoaLDBA   (LCRL LDBA)
            PrismBlackBoxMDP × HoaLDBA  ─ShapedLCRL.train_ql→  policy (Q-table)
                                        ─mc_evaluate→          P[property] under the policy
```
All in `src/netmdp/lcrl/` (`prism_mdp.py`, `props.py`, `owl.py`, `shaped.py`,
`workflow.py`). The one line to build a product is:
```python
from src.netmdp.lcrl.workflow import build_mdp_and_ldba
mdp, ldba, prop = build_mdp_and_ldba(pm_path, prop_index, constants=..., props_path=...,
                                     state_variables=[...])   # -> feed to LCRL
```

### Key building blocks (all reusable)
- `PrismBlackBoxMDP` — LCRL MDP API (`reset/step/state_label`, `current_state`,
  `action_space`) over any `.pm`. `state_variables` may include **callables**
  `fn(full_state)->value` for derived features (e.g. a bucketed congestion count).
- `PrismProperties` — reads a `.props`, translates each PRISM `P[...]` query to
  OWL LTL, lifts atoms (labels + relational predicates), errors on bounded
  operators. `prop.ldba`, `prop.label_fn()`.
- `ShapedLCRL(sign, reward_var, scale, drop_weight, ltl_weight, congestion_fn, …)`
  — LCRL with a dense reward (see METHODOLOGY §2a) and the native `+1`-at-accepting
  reward (`ltl_weight=1`). `mc_evaluate`, `greedy_action` are the eval helpers.

## 3. The three studies and how to run them
| study | model | question | direction |
|---|---|---|---|
| incast Pmax | `models/example2_desync_short_bursts/incast_mdp.pm` | worst-case incast loss | **max** (works) |
| incast Pmin | `.../incast_mdp_Pmin.pm` | is loss avoidable by scheduling? | min (hard) |
| fqcodel | `models/example3_fqcodel/fqcodel.pm` | worst-case traffic that over-serves flow 5 | max of a **rare** event (hard) |

```bash
# incast worst-case (Pmax) -- LCRL synthesises the synchronising schedule, P[Q]->1.0:
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py --M 16 --direction max
# DTMC/exact reference values, and exact Pmax/Pmin on small instances:
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/dtmc_reference.py
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/exact_bracket.py
# incast loss-avoidance (Pmin), forced-start model:
PYTHONPATH=. .venv/bin/python experiments/incast_mdp_lcrl/run_synthesis.py \
    --model incast_mdp_Pmin --M 16 --direction min
# fqcodel worst-case over-service:
PYTHONPATH=. .venv/bin/python experiments/example3_fqcodel/run_fqcodel.py
```

## 4. What is established (read METHODOLOGY for the evidence)
- **Maximising a *reachable* LTL event works well** (incast Pmax = 1.0; the
  `uniform_hazard` policy reproduces the DTMC exactly, validating the whole
  pipeline).
- **Two things are hard for tabular LCRL here:** (i) **minimisation** framed as a
  negative reward (optimistic-init pathology — always maximise the *complement*
  LTL property instead; but this alone was not sufficient); (ii) any target that
  is **rare** and needs precise multi-step control that a **lossy state
  projection** cannot represent — the deterministic greedy then does *worse* than
  random. Both incast Pmin and the fqcodel rare over-service hit this wall.
- Exact/SMC is the reliable route for the *value*; it does not scale, which is why
  the RL route matters.

## 5. What to try next (in rough priority order)
1. **Better state projections (cheapest lever).** Both hard cases fail because the
   tabular policy can't see the state that controls the outcome. Use
   `state_variables` with derived features (callables) to expose the *right*
   signal: incast → intra-slot concurrency; fqcodel → whether flows 1-4 are
   backlogged + flow 5's FQ-CoDel ranks. Iterate on which features let the greedy
   beat `random`/`uniform` (the diagnostic: mean of the target var vs baseline).
2. **A witness search for rare worst-cases.** For a value like fqcodel `Pmax`,
   before RL, confirm reachability and get a concrete offending trace with a
   directed/beam search over the simulator (`s._get_current_state()` +
   `s.restart(state)` let you save/restore). A witness both validates the property
   and seeds/《warm-starts》 RL.
3. **Function approximation.** The tabular Q-table cannot generalise across the
   huge product state. LCRL ships `train_nfq`/`train_ddpg`; or wrap the product in
   a small NN. This is the principled fix for the abstraction wall.
4. **Shorter effective horizon.** incast's `(MMAX+1)` substages inflate the
   horizon ~21x; a per-slot-collapsed model (see the retired init-phase Pmin
   variant in git history) learns far faster. Trade faithfulness for tractability
   deliberately.
5. **Always frame Pmin/avoidance as maximising the safe complement** (property (4)
   in each `.props`), never as a minimised reward.

## 6. File map
```
src/netmdp/lcrl/                     the library (MDP, props, OWL/LDBA, ShapedLCRL, workflow)
experiments/incast_mdp_lcrl/         METHODOLOGY.md + incast runners (run_synthesis, dtmc_reference, exact_bracket)
experiments/example3_fqcodel/        fqcodel runner (run_fqcodel.py)
models/example2_desync_short_bursts/ incast .pm/.props/NOTES (DTMC, incast_mdp, incast_mdp_Pmin)
models/example3_fqcodel/             fqcodel .pm/.props/NOTES
owl-macos-amd64-21.0/                bundled OWL (LTL->LDBA)
```
```
tip: runs are stochastic; compare the learned greedy against the random/uniform
baseline printed alongside it, and remember value@s0 is NOT the comparison
quantity on long horizons (Monte-Carlo-evaluate the policy). See METHODOLOGY §4.
```
