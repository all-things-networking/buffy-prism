# JANI vs PRISM as a compilation target for network languages

Status: discussion notes (2026-10-31), written to hand this thread to a new session. Claims marked
**(unverified)** were not checked against tool source or docs and should be confirmed before relying on them.
**Update 2026-11-01:** open question 1 is answered and every (unverified) claim has been checked; see the
corrections marked **[verified]** / **[corrected]** inline and the section "Results (2026-11-01)" at the end.
A Buffy → JANI / PRISM / SMT-LIB compiler now exists (`buffyc-mc`, Buffy repo branch `jani-backend`, here as the
`buffy` submodule).

## Question

We opted for JANI (https://jani-spec.org/) as the interchange format for the SMC / RL toolchain (Storm, the Modest
Toolset's `modes`, Momba). Is JANI a good compilation target for front-end network languages:

- **Buffy** (HotNets '24, doi:10.1145/3696348.3696854): queue/buffer programs with per-time-step semantics.
  (The paper itself was not re-read for these notes; comments are based on what `buffy-prism` models.)
- **ProbNetKAT** and its weighted, stateful, fully recursive descendants (https://netkat.org/).
- **P4V**: P4 verification via weakest preconditions + SMT.

And does the PRISM language differ from JANI in any meaningful way as such a target?

## Verdict

| Language | JANI fit | Reason |
|---|---|---|
| Buffy | **Good** | Bounded queues and per-step programs map to bounded ints/arrays and edges; traffic maps to probabilistic branches (DTMC) or named actions (MDP, for a scheduler / RL agent); devices compose as an automata network. `buffy-prism` already does this by hand in PRISM. |
| ProbNetKAT family | **Partial** | The guarded fragment over a single packet's state is a DTMC and compiles fine. Set/multiset-of-packets semantics (multicast, union) explodes as bounded arrays; history semantics and full recursion are not finite-state (bounded unrolling only); JANI rewards give one weight structure (expected sums), not general semirings. McNetKAT's specialised backend beat PRISM, so keep a dedicated backend for the core calculus and use JANI for stateful, traffic-level analyses. |
| P4V | **Poor** | Per-packet functional correctness under arbitrary control planes is WP + SMT over bit-vectors. JANI has bounded ints and no bit-vector type (**[verified]** no bitwise operators in core JANI or in any official extension; checked against the jani-model spec text); 32-48 bit headers make explicit or simulated state spaces hopeless. Only quantitative questions (e.g. misforwarding probability under a header distribution, with abstracted fields) would justify JANI. |

**Recommendation:** make JANI the primary analysis backend of a Buffy compiler. Generate one edge per time step, keep
arrays behind a feature flag (emit core JANI by default), emit traffic as probabilities or as named MDP actions for
the scheduler class, and add bounded-LTL monitors as extra automata.

## PRISM vs JANI: where they differ for a compiler

Expressively the cores are nearly equivalent: Storm converts PRISM to JANI automatically (done in this branch via
stormpy `program.to_jani([])`), and JANI was designed to subsume the PRISM language. The meaningful differences:

1. **Sequential updates within one step (favours JANI).** PRISM updates are simultaneous (every `x'=...` reads the old
   state). A per-time-step program with sequential effects (enqueue -> update lists -> dequeue) must either take
   several steps (the current `stage` variable; 11 or 16 steps per time step in the FQ-CoDel models) or be folded by
   the compiler into one simultaneous update. Folding is always possible, but each conditional doubles the number of
   guarded commands and expressions grow by substitution. JANI assignments carry an `index`, so the sequence can be
   emitted in order on one edge. Tool support for multiple indices varies (**unverified** for Storm and for `modes`).
   **[verified]** Storm's sparse/explicit builder, `mcsta` and `modes` all support multiple indices with sequential
   semantics, also across synchronised edges, and transient variables written at level k are readable at later
   levels. Storm's symbolic (DD) builder rejects assignment levels ("does not support assignment levels").
   **[corrected]** "Folding is always possible" is true in principle but not in practice. The paper's FQ scheduler
   folds to 953 DAG nodes, but written as an expression tree it has 7.5e14 nodes. PRISM and stormpy both expand
   `formula`s while *parsing*: at N = 2/3/4/5 queues, `prism -nobuild` takes 0.6 s / 36.7 s / >60 s / >60 s. A
   PRISM target therefore needs extra steps for the temporaries (the compiler's `--prism-temps stages`: 40 extra
   PRISM steps per time step for FQ), which is exactly the hand-written `stage` encoding again. In JANI, the
   temporaries are transient variables at assignment levels: 1 step per time step and no extra state.
   One edge per time step also makes step bounds count time steps and speeds up simulation.
2. **Data structures (favours JANI).** PRISM has bounded ints/bools and parameterless `formula` macros only, so a
   queue is one variable per slot and every index-dependent operation is unrolled; code size grows with buffer size.
   JANI's `arrays`, `datatypes` and `functions` extensions keep generated code close to the source. This is a
   compactness/debuggability/compile-time gain, not a checker-speed gain (Storm eliminates arrays into plain variables).
   **[verified]** Storm 1.13:
   - `arrays`: supported, eliminated into scalars `q_at_i`; 2-D arrays, dynamic indices and `ac` all work.
   - `functions`: supported, including array parameters; recursion is rejected.
   - `datatypes`: rejected at parse time.
   - Storm needs the model's `features` list: without it, arrays and functions fail with misleading errors.

   mcsta/`modes` 3.1.315 support all three, including recursive functions and datatypes, and ignore `features`.
   Out-of-bounds array indices are reported as errors by all tools.
3. **Composition (favours JANI).** In PRISM all modules sharing an action name synchronise, so wiring a topology needs
   renaming schemes. JANI uses explicit synchronisation vectors, so each link is stated directly; this matters once
   Buffy composes devices or a stateful NetKAT program spans switches.
4. **Temporal properties (favours PRISM).** The PRISM property language accepts LTL inside `P=? [...]` (checked by
   PRISM and Storm). LTL in JANI properties is not standardised, and `modes` handles reachability-style properties
   only. Workaround on the JANI side: compile bounded LTL to a DFA (e.g. Spot / an LTLf tool) and add it as a monitor
   automaton; the property becomes step-bounded reachability of the accepting state. That is also what incremental
   checking in importance splitting needs (monitor state is part of every anchor).
5. **Tool reach (favours emitting PRISM, slightly).** Emitting PRISM loses nothing since Storm converts it to JANI;
   emitting JANI loses PRISM itself, which (**unverified**) exports JANI but does not import it.
   **[corrected]** PRISM 4.10.1 neither imports nor exports JANI: there are no JANI classes in `prism.jar`, and the
   `-export*` options cover explicit/DRN/UMB formats only. `moconv`'s help lists `.nm` output, but this build
   accepts only JANI and Modest output. So no tool here turns JANI into PRISM. The compiler has separate JANI and
   PRISM emitters over one IR; neither uses Storm's PRISM→JANI conversion.
6. **Bounded G / W in properties (new, favours PRISM).** Neither Storm nor `modes` accepts bounded `G` or `W` in
   JANI properties: modes skips them as unsupported and Storm drops them. Only `U`/`F` reachability works.
   Storm's PRISM parser has no bounded `G` either. Both of the compiler's backends emit `G≤k φ` as the
   violation `F≤k ¬φ`, with min/max swapped.

No meaningful difference: probabilities, nondeterminism, rewards, step-bounded properties, finite-state limits.
Neither helps with recursion, packet sets or general semirings, and neither enforces action-label discipline (see the
bug below).

**Net:** for Buffy, items 1-3 favour JANI (sequential per-step programs over queues, composed into topologies) and item
4 is covered by monitors. For ProbNetKAT's guarded fragment and for P4V the two formats are interchangeable, and
neither is the right primary target.

## Practical lessons from this branch (JANI via Storm -> `modes`)

- `tests/modes/make_course_jani.py` builds the STAT 535C FQ-CoDel DTMC (Weibull traffic scheduler applied to the MDP)
  and exports JANI with stormpy. Needed fix-ups, all of which a native JANI emitter would do directly:
  - stormpy exports a single PRISM module's variables as automaton-local; JANI properties may only reference globals,
    so they are moved to the global scope.
  - Properties were written as JANI JSON by hand: step-bounded `U` under `Pmax`; the universal filter is spelled
    `"fun": "∀"` (not `"forall"`).
  - `modes --ifun-prop <name>` requires a named property whose expression is a bare state expression
    (`{"name": "imp", "expression": "iq5_deqs_bl"}`), not a filter.
- `modes` reads JANI and Modest only (no PRISM). Its `--help` is richer than the website docs: `--statistics` offers
  SPRT, ChowRobbins (the original rule with the `1/n` regulariser), Chen & Xu `Adaptive`, Hoeffding, Clopper-Pearson,
  DKW; `--rare Restart|FixedEffort|WeightedFixedEffort` with `--levels ExpectedSuccess`; `--cdf` exports per-run
  values; scheduler Q-learning and lightweight scheduler sampling exist. Install: `/Users/jkai/buffy-prism/Modest/modest`.
- Speed: a 154-step run costs about 45 us in `modes` (one thread), versus milliseconds per run with stormpy's Python
  simulator.
- Label discipline matters in any format: this repo's revised `fqcodel_5i_mdp.pm` gives the five arrival choices one
  shared label, and stormpy's `GLOBAL_NAMES` mode then always took 0 arrivals. The course model used distinct labels
  (`REC_PKT_ARR_IQi_Kk`). A compiler should emit distinct action names per choice.

## Open questions for the next session (status 2026-11-01 in brackets)

1. Check Storm's and `modes`' support for multi-index JANI assignments and the `arrays` / `datatypes` / `functions`
   extensions (their `features` handling), and whether PRISM can import JANI. [Done; see items 1, 2, 5 and the results.]
2. Prototype a Buffy -> JANI emitter for one device (FQ-CoDel), with one edge per time step; compare state counts and
   `modes` throughput against the 11-stage PRISM encoding. [Done for SMC. State counts were not compared:
   exact exploration at this size is intractable.]
3. Decide the bounded-LTL path: DFA monitor automata in JANI vs PRISM-language LTL with Storm. [Still open. The
   compiler's queries are bounded F / G / U only. Item 6 makes monitor automata more attractive.]
4. Re-read the Buffy paper to confirm which constructs (loops, queue ops, multi-device composition) the emitter must
   cover. [Done. The compiler covers bounded loops, `if`, `move-p`, `backlog-p`, queues
   (`enq`/`deq`/`has`/`empty`), `global`/`local`/`//@ monitor`, `assume`/`assert`, and multi-instance composition
   via `connect`. It does not yet cover `B |> F` filters or `move-b`/`backlog-b`, which need a class/byte-aware
   buffer model.]

## Results (2026-11-01)

### The compiler (`buffy` submodule, branch `jani-backend`; SMT-LIB target on `fperf-backend`)

`buffyc-mc` has three stages, documented in `buffy/docs/jani-backend.md`:
- **Front end:** a hand-written parser for the paper/URF syntax, plus a `network` block (capacities, traffic,
  connections, horizon) and bounded queries.
- **Elaborator:** produces BuffyImmut, a hash-consed DSA expression DAG of one time step. It unrolls loops,
  flattens arrays with switch-read/switch-assign, represents queues as slots plus a length, uses count buffers
  with tail drop, sets sticky `assume`/`assert` flags, and checks monitor non-interference.
- **Emitters:** separate JANI, PRISM and SMT-LIB emitters over that IR.

The layouts:
- **JANI sync** (default): one JANI step per time step. Traffic automata write transient arrival counts at
  level 0; a final `step` automaton evaluates the DSA temporaries as transient variables at levels 1..L and
  assigns the state at level L+1. MDP choices get distinct actions: one sync vector per joint choice.
- **JANI `--staged`**: one transition per traffic source, then the step.
- **PRISM**: staged arrivals; temporaries as formulas (small programs) or as one PRISM step per DSA level.
- **SMT-LIB**: T-step unrolling with symbolic workloads; queries are `check-sat`.

Regression tests (`buffy/test/jani`, `buffy/test/smt`) check four toy programs (SP, RR MDP, a two-instance
tandem, assume/assert):
- every JANI layout in Storm and mcsta, and both PRISM modes in Storm, against independent exact Python
  references, to 1e-9;
- the SMT answers against Storm (sat ⇔ Pmax > 0), including queries known to be unsat.

### Tool findings beyond the items above

- **Storm bug:** if an edge whose transient temporaries span several levels is followed, in the same
  synchronisation, by another synchronising edge, Storm silently drops the transition (a 1-state model). mcsta and
  modes are correct. Minimal reproducer: traffic automaton → `A` (`u := a` at level 1, `x := x + u` at level 2) → `E`
  (empty edge). Moving `E` before `A` works. The compiler works around it by putting all instances in one `step`
  automaton, synchronised last. This is worth reporting upstream.
- **Modest blocks actions that no sync vector mentions**, even in a one-automaton system (it builds a 1-state
  model). Storm is lenient. The staged layout therefore lists a trivial vector for every action.
- Storm rejects bare-expression properties (`{"name": "imp", "expression": "x"}`), which `modes --ifun-prop`
  requires. The compiler emits them only with `--importance-props`.

### FQ scheduler (paper Fig. 2) vs the hand-written 16-stage PRISM model — SMC only

Scripts and logs are in `experiments/buffy_jani/`. The models are N=5, SZ=8, K=4, T=14; queues 1–4 get uniform
0..4 arrivals, and iq5 gets P0 of none. The queries are evaluated at time-step boundaries. 100k runs each, one
thread.

Two things were found about the hand model on the way:
1. `tests/models/fqcodel_5i_dtmc_unif.pm` is **not uniform** for iq5: it uses 0.6/0.1/0.1/0.1/0.1, the
   "modified IQ5 distribution" run.
2. Its `G<=224` bound is **not 14 time steps**: a time step takes 11–16 PRISM steps depending on arrivals, so it
   covers 14–20. The comparison uses `stage=1 & time<=14` instead, with `time`, `cenq` and `aipg` made saturating
   (`experiments/buffy_jani/patch_hand_model.py`).

A violating trace sampled from the hand model replays step-for-step under a direct Python implementation of
Fig. 2, so the scheduler semantics agree.

| P(starve violated within 14 steps) | P0 = 0.2 (uniform) | P0 = 0.6 |
|---|---|---|
| direct Python Monte Carlo of Fig. 2 (`fig2_mc.py`, 200k) | 3.30e-4 ± 1.05e-4 | 1.204e-2 ± 6.3e-4 |
| hand model, `prism -sim` | 3.3e-4 ± 1.5e-4 | 1.158e-2 ± 8.7e-4 |
| compiled PRISM (46 steps / time step), `prism -sim` | 3.2e-4 ± 1.5e-4 | 1.174e-2 ± 8.8e-4 |
| compiled JANI sync, modes | 4.4e-4 [3.2e-4, 5.9e-4] | 1.191e-2 ± 6.8e-4 |
| compiled JANI staged, modes | 3.5e-4 [2.4e-4, 4.9e-4] | 1.175e-2 ± 6.7e-4 |

The other three queries (cond_a, early, gap) agree across models within their CIs as well. For example, the cond_a
violation at P0 = 0.6 is 0.8674 (hand), 0.8664 (compiled PRISM), 0.8670 (modes sync) and 0.8689 (modes staged).
PRISM CIs are 99%, modes CIs 95%. Logs: `experiments/buffy_jani/results/smc/`.

Wall-clock times for 100k runs:
- **modes on JANI sync:** 11.5 s for all four properties in one pass (115 µs/run, 14 JANI steps).
- **modes on JANI staged:** 73 s.
- **`prism -sim`, one query (starve):** 85 s on the hand model, 256 s on the compiled PRISM model at P0 = 0.2
  (98 s vs 240 s at P0 = 0.6). PRISM simulates each property separately.

So in modes, the sync layout's 1 step per time step is 6× faster than the staged layout. In PRISM, the compiled
model's 40 temporary stages cost about 3× against the hand-optimised 11–16 stages.

The netmdp session's native JANI simulator now supports levels, transient variables and synchronisation, and is
validating against these files.
