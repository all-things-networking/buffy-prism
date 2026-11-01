# JANI vs PRISM as a compilation target for network languages

Status: discussion notes (2026-10-31), written to hand this thread to a new session. Claims marked
**(unverified)** were not checked against tool source or docs and should be confirmed before relying on them.

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
| P4V | **Poor** | Per-packet functional correctness under arbitrary control planes is WP + SMT over bit-vectors. JANI has bounded ints and no bit-vector type (**unverified**: no bitwise operators in core JANI); 32-48 bit headers make explicit or simulated state spaces hopeless. Only quantitative questions (e.g. misforwarding probability under a header distribution, with abstracted fields) would justify JANI. |

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
   One edge per time step also makes step bounds count time steps and speeds up simulation.
2. **Data structures (favours JANI).** PRISM has bounded ints/bools and parameterless `formula` macros only, so a
   queue is one variable per slot and every index-dependent operation is unrolled; code size grows with buffer size.
   JANI's `arrays`, `datatypes` and `functions` extensions keep generated code close to the source. This is a
   compactness/debuggability/compile-time gain, not a checker-speed gain (Storm eliminates arrays into plain variables).
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

## Open questions for the next session

1. Check Storm's and `modes`' support for multi-index JANI assignments and the `arrays` / `datatypes` / `functions`
   extensions (their `features` handling), and whether PRISM can import JANI.
2. Prototype a Buffy -> JANI emitter for one device (FQ-CoDel), with one edge per time step; compare state counts and
   `modes` throughput against the 11-stage PRISM encoding.
3. Decide the bounded-LTL path: DFA monitor automata in JANI vs PRISM-language LTL with Storm.
4. Re-read the Buffy paper to confirm which constructs (loops, queue ops, multi-device composition) the emitter must
   cover.
