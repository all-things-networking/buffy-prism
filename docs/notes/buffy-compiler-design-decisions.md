# Buffy compiler: design decisions to review (2026-11-01)

These were made while running unattended, and each one is open to revision. The code is in the `buffy` submodule:
- branch `jani-backend`: JANI and PRISM;
- branch `fperf-backend` = `jani-backend` + the SMT-LIB and FPerf targets.

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

4. Value ranges are required for globals and monitors: `int<lo..hi>`, `queue<lo..hi>[cap]`. Locals need none,
   because they are transient. *Alternative:* infer ranges by interval analysis (the analysis now exists in
   `immut/Bounds`).
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

9. **Count buffers only** (the URF "tally" model): input buffers tail-drop at capacity, and output buffers start
   empty each step. Filters `B |> F` and `move-b`/`backlog-b` are rejected with an error; they need a
   class-aware buffer module, which is the next language feature to add.
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
    single `tick`.
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
