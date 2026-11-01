# Buffy → JANI / PRISM: FQ scheduler comparison

This compares models compiled with `buffyc-mc` (the `buffy` submodule, branch `jani-backend`) from the Buffy
paper's FQ scheduler (`buffy/examples/jani/fq_buggy.buffy`) against the hand-written 16-stage PRISM model
(`tests/models/fqcodel_5i_dtmc_unif.pm`). Everything is **statistical**. Exact model checking is intractable at
this size, so every run is capped with `timeout`.

| script | does |
|---|---|
| `make_models.sh` | builds `buffyc-mc` and writes `models/`: compiled JANI (sync, staged, `_imp` with an importance property), compiled PRISM, an MDP variant, and the patched hand models |
| `patch_hand_model.py` | hand model variants: iq5 P0 = 0.2 / 0.6, saturating `time`/`cenq`/`aipg`, and queries at time-step boundaries with `time<=14` (the original `G<=224` covers 14–20 time steps) |
| `run_smc.sh` | 100k runs each: modes (sync, staged), `prism -sim` (compiled, hand), and `fig2_mc.py` |
| `fig2_mc.py` | direct Python Monte Carlo of Fig. 2, independent of all models |
| `parse_time.sh` | how PRISM/stormpy parsing scales when temporaries are `formula`s, against staged temporaries |

Results and discussion: `docs/notes/jani-vs-prism-compilation-target.md`, section "Results (2026-11-01)". Raw logs
are in `results/`. `results/smc/` came from an equivalent earlier run of the same models, made by the same
compiler before the MDP-naming change, which leaves DTMC output unchanged. Re-running `run_smc.sh` writes
`results/*.log`.
