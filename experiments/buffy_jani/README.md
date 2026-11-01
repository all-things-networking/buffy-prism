# Buffy → JANI / PRISM: FQ scheduler comparison

This compares models compiled with `buffyc-mc` (the `buffy` submodule, branch `jani-backend`) from the Buffy
paper's FQ scheduler (`buffy/examples/jani/fq_buggy.buffy`) against the hand-written 16-stage PRISM model
(`tests/models/fqcodel_5i_dtmc_unif.pm`). Building the compiler needs ANTLR 4 (`brew install antlr antlr4-cpp-runtime`; see
`buffy/docs/parser.md`). Everything is **statistical**. Exact model checking is intractable at
this size, so every run is capped with `timeout`.

| script | does |
|---|---|
| `make_models.sh` | builds `buffyc-mc` and writes `models/`: compiled JANI (sync, staged, `_imp` with an importance property), compiled PRISM, an MDP variant, and the patched hand models |
| `patch_hand_model.py` | hand model variants: iq5 P0 = 0.2 / 0.6, saturating `time`/`cenq`/`aipg`, and queries at time-step boundaries with `time<=14` (the original `G<=224` covers 14–20 time steps) |
| `run_smc.sh` | 100k runs each: modes (sync, staged), `prism -sim` (compiled, hand), and `fig2_mc.py` |
| `fig2_mc.py` | direct Python Monte Carlo of Fig. 2, independent of all models |
| `parse_time.sh` | how PRISM/stormpy parsing scales when temporaries are `formula`s, against staged temporaries |
| `run_rare.sh` | rare-event benchmark: modes plain MC vs importance splitting (RESTART, fixed effort; compiled hint vs automatic) on the starve property at P0 = 0.2, to a ±10% relative 95% CI |

Further results (second round, compiler branch `features`):
- `results/prism_merged/`: `prism -sim` (20k runs, starve, P0 = 0.6) on the compiled model with `merged` stages
  (11 PRISM steps per time step) vs per-level `stages` (46) vs the hand model.
- `results/choose/`: modes with uniform resolution on the mixed FQ MDP (`fq_buggy_mdp_mixed.buffy`) in the
  `choose` and `staged` layouts; must equal the DTMC at the same P0.
- `results/rare/`: `run_rare.sh` output.

Results and discussion: `docs/notes/jani-vs-prism-compilation-target.md`, section "Results (2026-11-01)". Raw logs
are in `results/`. `results/smc/` came from an equivalent earlier run of the same models, made by the same
compiler before the MDP-naming change, which leaves DTMC output unchanged. Re-running `run_smc.sh` writes
`results/*.log`.
