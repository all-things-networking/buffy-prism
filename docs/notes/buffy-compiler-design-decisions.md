# Buffy compiler: design decisions to review (2026-11-01)

These were made while running unattended, and each one is open to revision. The code is in the `buffy` submodule,
which tracks Buffy `main`. It was developed on branches that are now merged and deleted: `jani-backend`
(decisions 1–19), `features` (20–31, 34, 35) and `fperf-backend` (32, 33, and the SMT-LIB and FPerf targets).

The decisions are numbered in the order they were made. A later one can replace an earlier one; such entries
are marked *Superseded*, and the current behaviour is in the decision named there.

The [user guide](../../buffy/docs/user-guide.md) (`buffy/docs/user-guide.md`) documents the result.

Background: `docs/notes/jani-vs-prism-compilation-target.md`, Buffy `docs/jani-backend.md` and
`docs/fperf-backend.md`.

## Architecture

1. **The C++ compiler lives in the Buffy repo, with a new, separate AST.** The existing `buffy::ast` classes have
   no accessors, slice `Typ` by value, and are wired into the unfinished FPerf skeleton, so I left them untouched.
   The new code is:
   - a uniformly-shaped syntax AST (`include/frontend/Syntax.hpp`) with a hand-written recursive-descent parser,
     instead of ANTLR (which would have added a dependency);
   - BuffyImmut as a hash-consed DSA expression DAG (`include/immut/`) rather than an AST of `:=` statements.

   *Superseded* in two parts: the old skeleton was deleted (34), and the hand-written parser was replaced by an
   ANTLR 4 grammar (35). The syntax AST and BuffyImmut are unchanged.
2. **One elaboration for all backends, by symbolic execution of one time step.** This does loop unrolling (for
   loops have an *exclusive* upper bound, as the paper's `for (i in 0..N)` over `ibs[i]` requires), array
   flattening with switch-read/switch-assign, DSA and ite-joins in one walk. The result is a single simultaneous
   update per state variable. Backends differ only in how they name shared DAG nodes:
   - JANI: transient variables at assignment levels;
   - PRISM: formulas or temp stages;
   - SMT: constants defined by equalities;
   - FPerf: Z3 terms.
3. **PRISM and JANI are separate emitters.** Nothing uses Storm's PRISM→JANI conversion (per your instruction).

## Language extensions (all new syntax)

4. Value ranges for globals and monitors: `int<lo..hi>`, or inferred when left out (decision 21). Queues still
   need `queue<lo..hi>[cap]`. Locals need none, because they are transient.
5. **Buffer direction is inferred.** A parameter is an input if it is a `move-p` source or receives traffic or a
   connection, and an output otherwise. Explicit `in`/`out` keywords are optional.
6. **A `network { ... }` block** declares `instance`, `capacity`, `traffic ~ uniform | nondet | bernoulli | {k: p}`,
   `connect a.ob -> b.ibs[i]`, `init`, and `horizon T` (which adds a saturating `time` variable).
   **`query name: P|Pmax|Pmin=? [F<=T e | G<=T e | e U<=T e];`** declares queries, with bounds in time steps.
   **`importance name: e;`** declares a splitting hint.
7. **`arrivals-p(b)` / `drops-p(b)`** observe the current step's traffic, which monitors like FPerf's
   cenq/aipg need. This isn't in the paper.
8. **`assume`/`assert` become sticky flags** (`inst.assume_violated`, `inst.assert_failed`) rather than pruning or
   conditioning. Conditioning is left to the query, e.g. P(φ ∧ G¬violated) / P(G¬violated).

## Semantics choices

9. **Count buffers** (the URF "tally" model) when the program has no `packet` declaration: input buffers
   tail-drop at capacity, and output buffers start empty each step. With packet classes, see decision 20.
10. **Queues:**
    - `enq` on a full queue is a no-op;
    - `deq` on an empty queue returns `lo` and leaves the queue unchanged;
    - unused slots are kept at `lo`, so states are canonical;
    - `deq()` must be the whole right-hand side of an assignment.
11. **Composition** follows the paper: an output is flushed into its connected input at the end of the step, and
    the downstream instance sees the packets in the next step. A step has two phases: arrivals, then every
    instance's program on the post-arrival state.
12. **Out-of-range values are errors, not saturation**, matching the tools' behaviour. `--saturate` clamps the
    globals. The FQ example saturates its monitors explicitly, because SMC and exact exploration step past the
    query horizon.

## Backend choices

13. **The default JANI layout is "sync"** (1 JANI step per time step), with all instances in one `step`
    automaton synchronised last. That is a workaround for a Storm bug, and it makes per-instance automata
    cosmetic only (each assignment's comment names its instance). `--staged` gives 1 + S steps per time step;
    `--no-levels` gives a core-JANI single update for small programs, and is refused above 2·10⁶ tree nodes.
14. **MDP action naming:** every nondeterministic choice gets its own action. The sync layout uses one sync vector
    per joint choice (`tick_k1_..`), up to 4096 combinations, beyond which `--staged` is required. DTMCs use a
    single `tick`. For simulation and RL, the staged layout's factored choices are much cheaper (63 ns/step vs
    3.5 µs/step natively on the FQ MDP), and the compiler recommends it above 64 joint choices.
    *Superseded* in part by 30: that alternative became the `choose` layout, which is now the default above 64
    joint choices instead of the recommendation to use `--staged`. Per-choice action naming is unchanged.
15. **`G` is emitted as `<name>_violation` = `F ¬φ`, with min/max swapped**, in JANI, PRISM and SMT alike. Neither
    Storm nor modes accepts bounded G in JANI, and Storm's PRISM parser lacks bounded G.
    *Alternative:* emit native `G` in the PRISM files for PRISM-only use.
16. **PRISM temporaries:** `auto` picks formulas below 2·10⁶ tree nodes and *temp stages* above that, because both
    PRISM and stormpy expand formulas at parse time. Temp stages cost L extra PRISM steps per time step: 40 for FQ,
    46 steps per time step in total. *Alternative:* multi-level merging, i.e. putting independent levels in one
    stage. A stage already holds all temporaries of one level, so the count is the DAG depth.
    *Superseded* by 29: that alternative became `merged` temp stages, which `auto` now picks above 2·10⁶ tree
    nodes (11 PRISM steps per time step on FQ). Per-level stages remain available as `--prism-temps stages`.
17. **SMT-LIB semantics are qualitative:** traffic is a symbolic workload over the distribution's support, and a
    query asks "sat ⇔ some workload realises it" (⇔ Pmax > 0). FPerf-style workload constraints in Buffy syntax
    are not yet available. You can add assertions by hand, or use the FPerf backend.
    *Superseded* in part by 33: network `assume`s and `given assumptions` now constrain the workload.
18. **The FPerf backend evaluates the DSA DAG directly over FPerf's queue variables**, instead of the URF's
    wp + `$IN_*`/`$OUT_*` substitution. Output packet identity comes from recorded `move-p` events. Only one
    instance per contention point is supported so far, and Buffy `traffic` is ignored (FPerf's workload drives
    the inputs).
    *Superseded* in part by 32: several instances per contention point are now supported. Buffy `traffic` is
    still ignored.

## Testing policy

19. **Exact checks are for toy models only:** SP, the RR MDP, the tandem composition, and assume/assert, against
    independent Python references. Every layout is checked in Storm and mcsta, and SMT answers against Storm.
    FQ-size models are compared **only by SMC** (modes, `prism -sim`) and with a direct Python Monte Carlo of the
    paper's Fig. 2, always under `timeout`.

## Second round (2026-11-01): additions on branch `features`

20. **Packet classes.** `packet { int<lo..hi> field; ... }` makes every combination of field values a class
    (at most 4096). Filters are `B |> pred` over fields, constants and program variables, allowed in move
    sources, `backlog-p`/`backlog-b`, `arrivals-p`/`drops-p` and traffic. Each buffer is stored either as
    **per-class counts** or as a **FIFO sequence** of class ids (slots plus a length; unused slots 0), chosen
    per buffer: counts when every move out of it "pins" one class (its filter conjunction contains
    `field == e` for every field, with e free of fields), FIFO otherwise. This matches the URF slides' choice
    between tuples and multiscale (count) buffer models. `--fifo-buffers` forces FIFO everywhere; the tests
    check that both representations agree. Output buffers are always FIFO with classes (they cost no state).
    *Alternatives:* always FIFO (exact but far more states); multisets with a fixed tie-break (inexact).
21. **`move-b(src, dst, n)`** moves the longest FIFO prefix of (matching) packets whose total size is at most
    n, so a head packet that does not fit blocks the rest (no partial packets). Sizes come from a field named
    `size`; without one every packet is 1 byte. `backlog-b` sums sizes.
22. **Traffic with classes:** each source must select exactly one class (a filter of constants), and a buffer
    may have one source per class. Several sources into one buffer arrive in declaration order within a step,
    which decides tail drops. The emitters no longer build arrival updates: the elaborator gives each staged
    arrival transition its updates.
23. **Range inference:** the least fixpoint of interval analysis over the step from the initial value, with
    widening to the program's constants (±1) and one narrowing pass; a variable still growing at 2⁴⁰ is
    an error that asks for a saturating range. Sound but can over-approximate (RR's `last` gets −1..2).
24. **Queries are bounded LTL** over state predicates (F/G/X/U with step bounds, `! && || ->`). A single
    unnested F/G/U keeps the old direct encoding; everything else becomes a **deterministic monitor** built
    at compile time by formula progression (NNF, interned formulas, states enumerated by BFS over the atom
    valuations, ≤ 16 atoms per state, ≤ 100k states). The monitor's update reads the values the step
    computes, and the initial state is folded in at compile time, so it observes time-step boundary states
    in every layout (sync, staged, choose, PRISM). The property is `F<=H mon = accept`. This answers open
    question 3 of the JANI-vs-PRISM note in favour of monitors, which work for every target, SMC included.
    *Alternative:* PRISM-language LTL (Storm/PRISM only, no SMC with modes).
25. **`given ψ`:** for DTMCs, two properties `<q>_joint` = P(φ ∧ ψ) and `<q>_given` = P(ψ), whose ratio is the
    conditional probability. For MDPs, `Pmax` uses φ ∧ ψ and `Pmin` uses φ ∨ ¬ψ, so violating paths count
    against the optimiser; this is the constrained optimum when ψ only restricts nondeterministic choices and
    can always be respected. `given assumptions` = no assumption flag set within the formula's horizon.
    *Alternative:* Storm's conditional properties (reachability conditions only, Storm only).
26. **Network assumptions** `assume e;` (in the network block) read globals and monitors before the step and
    this step's `arrivals-p`/`drops-p`, but not buffers (which differ between layouts at that point). A
    violation sets the sticky `assume_violated`. With monitors for memory, these express the slides' path
    conditions (`examples/jani/deck_rr.buffy`).
27. **`--prune-violations`:** the violating step leads to one absorbing sink (all state except flags and
    monitors reset to initial values), the slides' "prune on path-condition violation". It is off by default
    because it makes queries that do not exclude violations meaningless.
28. **Staged layouts resolve nondeterministic sources before probabilistic ones** (keeping per-buffer order),
    so a scheduler never sees the current step's probabilistic arrivals before choosing, as in the sync layout.
    This was a semantic difference between layouts before.
29. **PRISM `merged` temp stages** (the new `auto` choice above 2·10⁶ tree nodes): consecutive DAG levels are
    grouped while every inlined expression stays below 4096 tree nodes (`--prism-stage-size`); only
    temporaries read by a later stage are variables; the last group is folded into `[step]`. FQ: 11 instead of
    46 PRISM steps per time step, 104 instead of 165 bounded variables, a 460 KB instead of 32 KB file, and
    `prism -sim` as fast as on the hand model.
30. **JANI `choose` layout** (agreed with the netmdp session): each nondeterministic source chooses on its own
    edge (`arr_<src>_<k>`, ordered by a `turn` variable) into a persistent bounded variable; one `tick` then
    runs the step with the probabilistic sources. It is the default for MDPs with more than 64 joint choices
    (`--layout auto`). Property bounds are scaled by (choices + 1) and evaluated at `turn = 0`; a `time`-based
    bound was rejected because it needs a `horizon`.
31. **JANI properties never reference step temporaries** (a latent bug: a query atom identical to a shared
    step node was printed as the transient's name, which Storm rejects in the staged layout).

## Second round: additions on branch `fperf-backend`

32. **Multi-instance FPerf:** one queuing module per instance, linked with FPerf queue edges as `connect`
    says. FPerf's queue semantics (an output's enqueues land at the tail of the linked queue at the next step,
    tail-dropped at its size) equal Buffy's flush. Connected inputs use their value before the flush for
    `deq_cnt`; modules share per-step state variables. Packet classes are rejected in FPerf for now.
33. **SMT workload constraints** use network assumptions plus `given assumptions` rather than new syntax.
34. **The old AST/visitor/SMTIR skeleton is removed** (at your request): the old AST classes, visitors,
    SMTIR, the wp/`fperfRunner` backend, its test harness, the hand-translated IR examples and the
    Z3-4.8.11 build. The URF report's source examples moved to `examples/urf/`.
35. **The parser is an ANTLR 4 grammar** (`grammar/Buffy.g4`, at your request), replacing the hand-written
    recursive-descent parser behind the same `frontend::parse` API. Before the switch both parsers produced
    identical ASTs (with source locations) on every example and edge case, byte-identical JANI/PRISM output,
    and the same decisions on 25,500 fuzzed programs; golden AST dumps from the hand parser now guard the
    grammar (`test/parser`). Semantic predicates keep Buffy's one-token decisions (no reserved words).
    `make mc` now needs the ANTLR tool (Java) and C++ runtime. Syntax errors other than lexical ones are
    ANTLR's messages.

## Independent review (2026-11-01)

A separate reviewer (Fable) read the whole compiler on `fperf-backend`, ran every suite and probed it
with small programs. Accepted and fixed (in Buffy `features` c9dcbd0 and `fperf-backend` d322fac, both in `main`):
- **Unsound `%` interval rule** in `immut/Bounds` (a model could violate its inferred range), and a
  too-coarse `/` rule (bounded halving counters were rejected as unbounded).
- **SMT queries referenced step temporaries** at the last position; z3 rejected the assertion and
  answered `sat`. Queries are now printed over state variables only, and the SMT test fails on any
  z3 error.
- **`%` differed between paths** for negative operands (Storm/mcsta floor modulo vs C remainder in
  Z3 and the constant folder). JANI and PRISM now emit C's remainder unless both operands are
  provably non-negative.
- `init` on queues/buffers rejected and initial values type-checked; literal overflow and bad
  numeric options reported instead of aborting; errors carry source positions.
- Design: the LTL machinery moved to `immut/Ltl`, range inference to `immut/Bounds`; an RAII guard
  restores the elaborator's modes; connections are kept in network order; FPerf output queues are
  sized from their enqueues.
- Tests: `examples/jani/arith` (negative `%`/`/`, inference over them, a query atom shared with the
  step), pruning in every layout, `-D` overrides, and 12 elaborator error cases (`test/elab`).

36. **Declined: block-scoped locals.** The reviewer suggested lexical scoping for `local`. The paper's
    `local x = e` re-assignment form implies method-scoped locals, so they stay method-scoped (a name is
    declared once per method); the user guide now says so.


## Third round (2026-11-01): bursty traffic and model-checking efficiency

37. **Bursty traffic as phases plus state-dependent distributions.** `phase x = init ~ D;` is a
    network-level state variable redrawn from `D` every step, and `traffic b ~ c ? D1 : D2` makes a
    distribution depend on the state. A phase is a source without a buffer whose drawn value the step
    takes over (`Δ(x) = α_x`), so methods, monitors and other sources read its boundary value in every
    layout, and the scheduler's information pattern is unchanged. Conditions may read globals,
    monitors and phases, but not buffers (layout-dependent mid-step) or `arrivals-p`/`drops-p`.
    Branches must be probabilistic. JANI/PRISM get probability expressions; SMT-LIB gets per-value
    possibility conditions; FPerf rejects phases.
    *Alternatives:* a dedicated `markov { ... }` source syntax (less general: no dependence on
    globals or other phases); random globals updated inside methods (would break the deterministic
    step).
38. **Monitors are minimised** by Moore partition refinement whose signatures are reduced ordered
    decision diagrams over the atoms, with `true` kept apart so that acceptance times are preserved.
    Atoms are treated as independent inputs (sound, possibly incomplete).
39. **`--auto-importance`** derives an importance function per query: the progress of the target
    predicate (comparison gaps from interval analysis, `&&` adds, `||` takes the best), refined for
    monitor queries by the monitor's distance to acceptance. Its target value is reached exactly at
    the target states, as `modes --ifun-prop` requires; splitting stays unbiased whatever its quality.
40. **The choose layout applies nondeterministic arrivals on their own edges** (as staged does) and
    keeps a register only for a source that an earlier-declared probabilistic source precedes into the
    same buffer (tail-drop order). It never has more states than the register version (`rr`: 1,479
    against 4,320).
41. **Rewards and expected values.** `reward r: e;` is earned once per time step, with `e`
    evaluated at the end of the step (state after the step, the step's own `arrivals-p`/`drops-p`);
    queries `E{r}`/`Emax{r}`/`Emin{r}=? [ C<=k | I=k | F φ | S ]`. Rewards add no state: a transient
    JANI variable on the step edge, a PRISM transition reward on `[step]`. Bounds are scaled by the
    transitions per time step; long-run averages use the reward times that number, so `S` is per time
    step in every layout. State reads in a reward become placeholders substituted by the updates, so
    `drops-p` keeps its in-step meaning. SMT-LIB skips expected-value queries.
    *Alternative rejected:* monitor counters as reward proxies (they multiply the state space, cannot
    express long-run averages or expected times, and per-threshold MDP optima only bound `Emax`).
    Tool support measured: Storm all forms (JANI and PRISM); `mcsta` only `F`.
42. **Case-study programs use the language as it is.** `incast.buffy` and `llm_sched.buffy` reproduce
    the hand-written PRISM models of the incast and LLM batch-scheduler case studies exactly (every
    property to 1e-15 on small configurations; full size within SMC error). Per-step random draws that
    a method needs in the same step are arrival counts of a capacity-0 buffer; sender and request
    state are method globals. PRISM's one-value ranges (`[0..0]`) are emitted one wider. The design
    gaps these programs expose (stopping at the horizon, first-class draws, sources with memory,
    `drops-p` for moves, selection loops, at-horizon queries, exact probability literals) are listed
    in `experiments/buffy_case_studies/README.md`; only the first is implemented (43).
43. **`--stop-at-horizon`** freezes the state once `time` reaches the horizon:
    every step update and staged arrival update becomes `time < H ? update : current value`.
    Draws past H still happen but return to the same state. The option is opt-in because it
    changes the model's meaning beyond H. Each query is checked against the horizon (bounded
    `F`/`G`/`U` and monitor horizons ≤ H; `E` only as `C<=k`/`I=k` with k ≤ H), with the error
    at the query.
    *Alternatives:* applying it automatically whenever every query qualifies. Rejected, because
    tools and users read the emitted model with other properties too. A separate sink state was
    also rejected: it would lose the state at H that the at-horizon queries read.
44. **Random and nondeterministic choices inside methods: `x ~ D;`.** `D` is any traffic distribution:
    constant, conditional on the instance's state at the time-step boundary, or `nondet` (an MDP
    choice). Every occurrence, after loop unrolling, is a source of its own (`Traffic::draw`: no
    buffer, no state) drawn in every step, whose value the statement assigns. The step stays a
    deterministic function of the state and the step's draws, so the factored structure and every
    backend carry over. In JANI and PRISM a draw is a bufferless source like a phase without memory.
    In FPerf it is a free value restricted to its possible values, which is FPerf's own
    nondeterminism. Nondeterministic draws are resolved before the step's probabilistic ones, from
    the boundary state, as nondeterministic traffic is. This supersedes the capacity-0 buffer idiom
    (`arrivals-p` of a dropped source), which gave identical models in every layout
    (`test/jani/same/`).
    *Alternative rejected:* distributions that depend on values computed in the step. They would
    need sequential sampling inside the step (no sync layout) and would break the deterministic
    step. A draw over a fixed range mapped onto the candidates covers the common case.
45. **FPerf backend for multi-device networks.**
    - Packet classes map to FPerf metadata (fields in order: `meta1`, `meta2`) over FIFO storage.
    - Buffers that a program fills itself are module state rather than FPerf queues.
    - External inputs can be same-step `IMM_QUEUE`s, which is Buffy's own order.
    - Output packets come from the output buffers' final contents.
    - `BuffyNet` builds the modules inside any contention point. `fperf_equiv_test` uses it to check
      each hand-written FPerf CP against its Buffy program for every workload up to a horizon, with
      pins for FPerf's nondeterministic choices and a refinement check for the crossbars.

    See `docs/notes/fperf-cps-in-buffy.md`.
46. **`connect a.ob -> b.ib immediate;`** delivers what `a` puts into `ob` to `b.ib` in the same step:
    after `b.ib`'s own arrivals and before `b`'s step, with tail drop. Instances are elaborated in a
    topological order of the immediate connections (a cycle is an error, reported at a connection),
    and the network step stays one simultaneous update, so JANI, PRISM and SMT-LIB need nothing new.
    In FPerf, instances joined by immediate connections form one module whose immediately connected
    inputs are internal state. Reading FPerf's `IMM_QUEUE` there would count the same-step packets
    twice, because the DAG already appends them.

    `tandem_immediate.buffy` equals the same tandem fused into one method in every layout.
    `loom_modular.buffy`, with one instance per FPerf module, is as equivalent to FPerf's Loom as the
    one-method version.

    *Alternative rejected:* a global "all connections immediate" mode. It cannot express the leaf-spine
    fabric, whose links between switches deliver at the next step while its stages within a switch
    deliver in the same step.
47. **A draw's condition may read the variables of enclosing loops.** `snd[i] ~ w[i] == 1 ? D1 : D2;`
    in a loop over `i` is one state-dependent source per `i`. Conditions are resolved after elaboration
    (they read the boundary state, not the step's values), outside the loop's scope, so each
    conditional draw now records the loop variables in force where it was drawn and restores them when
    its condition is resolved. The outcast case study (`examples/jani/outcast.buffy`, TCP senders whose
    rate depends on their window) needed it. `draws_loop.buffy` equals a hand-unrolled copy in every
    layout (`test/jani/same/`).

    *Open:* bounded LTL with long time windows. A conjunction of two `F<=80` windows exceeds the
    100,000-state monitor limit, because formula progression gives each conjunct a countdown that
    duplicates `time`. Time-anchored or factored monitors would avoid this
    (`docs/notes/case-study-outcast.md`).
48. **Factored LTL monitors.** A query whose top level (in negation normal form) is an and/or of
    temporal subformulas may get one monitor per subformula, with the property
    `F<=depth (and/or of mon_i = accept_i)`. This is exact because a bounded subformula's verdict is
    absorbing and the combination is positive. Equal subformulas share a monitor, so a `given`
    condition is built once for `_joint` and `_given`. A single monitor is still tried first while it
    stays under 20,000 states, since it is minimised as a whole. `--factor-monitors` forces factoring;
    `test/jani` checks every exactly checked example both ways. This resolves decision 47's open
    item: the outcast study's learned conditions, two `F<=80` windows each, now compile as `given`
    queries.

    Monitor updates now select the successor by binary search on the state index (depth log2 N). The
    linear `ite` chain overflowed the JANI emitter's stack at tens of thousands of states.

    *Alternative rejected:* time-anchored progression (reading `time` instead of each `F<=b`'s own
    countdown). It only helps formulas evaluated from a fixed position, and it needs knowledge that
    `time` is monotone, which formula progression does not have.
49. **`--condition-on <query>`: conditioning the input exactly.** For a query's `given` condition
    psi that depends on the random input through one probabilistic source:
    - the compiler closes psi's variables under their updates (the input cone) and enumerates
      (step, cone state, psi-monitor state) up to psi's depth;
    - it computes h by backward induction and replaces the source's probabilities by
      `p * h_{t+1} / h_t`, selected by a new state variable `cond_<q>` (a balanced lookup).

    The resulting DTMC's path law is the original one conditioned on psi (Doob's h-transform).
    Everything outside the cone depends on the source only through its draws, so it is unchanged.
    P=? of the query's formula is `P(phi | psi)`, and `P(psi) = h_0` is exact. This turns the rare
    condition problem of the FQ study, P(A) of 1e-3 to 1e-7, into ordinary simulation
    (`experiments/buffy_conditioning`). It is the probabilistic counterpart of building the model
    on demand while pruning paths that violate a path condition (Automata 2025 slides).

    *Restrictions:* a DTMC, and one source; several sources in one step would need their draws
    sequenced within the step. A closed-loop input, where the source's distribution depends on
    state it does not drive alone (the outcast study), is outside the cone and rejected.

    *Alternative rejected:* importance weights in the simulator. They need simulator support for
    reweighting probabilistic edges, and they give unbiased but higher-variance estimates. Here the
    weights cancel exactly.
