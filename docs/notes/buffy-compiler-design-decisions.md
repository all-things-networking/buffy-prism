# Buffy compiler: design decisions to review (2026-11-01)

These were made while running unattended, and each one is open to revision. The code is in the `buffy` submodule:
- branch `features` (= `jani-backend` + decisions 20–31, 34, 35): JANI and PRISM;
- branch `fperf-backend` = `features` + the SMT-LIB and FPerf targets.

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

   *Revisit:* migrating the old visitor/SMTIR skeleton onto this front end, or deleting it.
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
    *Alternative* (suggested by the netmdp session): a sync-like layout in which each traffic automaton chooses
    on its own interleaved edge before the synchronised step.
15. **`G` is emitted as `<name>_violation` = `F ¬φ`, with min/max swapped**, in JANI, PRISM and SMT alike. Neither
    Storm nor modes accepts bounded G in JANI, and Storm's PRISM parser lacks bounded G.
    *Alternative:* emit native `G` in the PRISM files for PRISM-only use.
16. **PRISM temporaries:** `auto` picks formulas below 2·10⁶ tree nodes and *temp stages* above that, because both
    PRISM and stormpy expand formulas at parse time. Temp stages cost L extra PRISM steps per time step: 40 for FQ,
    46 steps per time step in total. *Alternative:* multi-level merging, i.e. putting independent levels in one
    stage. A stage already holds all temporaries of one level, so the count is the DAG depth.
17. **SMT-LIB semantics are qualitative:** traffic is a symbolic workload over the distribution's support, and a
    query asks "sat ⇔ some workload realises it" (⇔ Pmax > 0). FPerf-style workload constraints in Buffy syntax
    are not yet available. You can add assertions by hand, or use the FPerf backend.
18. **The FPerf backend evaluates the DSA DAG directly over FPerf's queue variables**, instead of the URF's
    wp + `$IN_*`/`$OUT_*` substitution. Output packet identity comes from recorded `move-p` events. Only one
    instance per contention point is supported so far, and Buffy `traffic` is ignored (FPerf's workload drives
    the inputs).

## Testing policy

19. **Exact checks are for toy models only:** SP, the RR MDP, the tandem composition, and assume/assert, against
    independent Python references. Every layout is checked in Storm and mcsta, and SMT answers against Storm.
    FQ-size models are compared **only by SMC** (modes, `prism -sim`) and with a direct Python Monte Carlo of the
    paper's Fig. 2, always under `timeout`.

## Additions on branch `features` (2026-11-01, second round)

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

## Additions on branch `fperf-backend`

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
with small programs. Accepted and fixed (Buffy `features` c9dcbd0, `fperf-backend` d322fac):
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

