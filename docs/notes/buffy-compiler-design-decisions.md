# Buffy compiler (buffyc-mc): design decisions

This note records the design decisions of buffyc-mc, the compiler from Buffy programs to probabilistic
models and simulators, with the reason for each. Every decision is open to revision. The code is in the
`buffy` submodule. Decisions 1–46 are on Buffy `main`. Decisions 47–58 are on the branch
`outcast-case-study`, which is not merged into `main`; the submodule points at it.

**Related documents.**
- The formal specification is Buffy's `docs/compilation`; `make` builds `buffy-compilation.pdf`.
- The user guide is [`buffy/docs/user-guide.md`](../../buffy/docs/user-guide.md).
- Buffy's `docs/jani-backend.md` and `docs/fperf-backend.md`.
- `docs/notes/jani-vs-prism-compilation-target.md`.

**Labels.** Other notes cite decisions by number, so the numbers are stable labels; the note is ordered by
topic, not by number. Where one decision contains another, the contained number is listed with it. The
index at the end gives every number's section.

**Terms.**
- *The Buffy paper*: the HotNets'24 paper that introduced Buffy.
- *URF*: the report *Specification of the Buffy Compiler*.
- *FQ*: the paper's fair-queuing scheduler (`examples/jani/fq_buggy.buffy`).
- *SP* and *RR*: the strict-priority and round-robin examples (`sp.buffy`, `rr.buffy`).

## 1. Architecture and front end

**1 (contains 34) — A syntax AST and a DAG intermediate representation.** The compiler is C++ in the
Buffy repository. It has two layers:
- a uniformly shaped syntax AST (`include/frontend/Syntax.hpp`);
- BuffyImmut (`include/immut/`), a hash-consed expression DAG in dynamic single assignment form, rather
  than an AST of `:=` statements.

The modules are `Expr` (the DAG), `Elaborate`, `Bounds` (interval analysis and range inference), `Ltl`
(monitors), `Sharing` and `Model`.

The URF report's AST classes were not reused: they have no accessors, slice types by value, and are
tied to a wp-based FPerf skeleton. That AST, its visitors, its SMT IR and the wp backend are not part
of the compiler. The URF's source examples are in `examples/urf/`.

**35 — An ANTLR 4 grammar.** The parser is `grammar/Buffy.g4` behind `frontend::parse`. Golden AST dumps
guard it (`test/parser`). Semantic predicates keep Buffy's one-token decisions, so the language has no
reserved words. Building needs the ANTLR tool (Java) and its C++ runtime. Syntax errors other than
lexical ones are ANTLR's messages. The front end also:
- rejects `init` on queues and buffers, and type-checks initial values;
- reports literal overflow and invalid numeric options;
- attaches a source position to every error.

**2 — One elaboration for every target.** Elaboration symbolically executes one time step. In one walk
it does loop unrolling, array flattening with switch-read and switch-assign, dynamic single assignment,
and `ite` joins. `for` loops have an exclusive upper bound, as the paper's `for (i in 0..N)` over
`ibs[i]` requires. The result is one simultaneous update per state variable. The JANI, PRISM, SMT and
FPerf backends differ only in how they name shared DAG nodes:
- JANI: transient variables at assignment levels;
- PRISM: formulas or temporary stages;
- SMT: constants defined by equalities;
- FPerf: Z3 terms.

The native target is the exception. It generates the program's step as structured C (54) and uses the
DAG only for the updates outside the program, or for the whole step under `--native-dag`.

**3 — JANI and PRISM are separate emitters.** Neither output is converted from the other, and nothing uses
Storm's PRISM-to-JANI conversion. Converting PRISM to JANI would inherit PRISM's lack of transient
variables, so every temporary would become a tree or a staged state variable.

## 2. Source language

**4 — Value ranges.** Globals and monitors have `int<lo..hi>` ranges, which are inferred when left out
(23). Queues need `queue<lo..hi>[cap]`. Locals need no range, because they are not state.

**23 — Range inference.** A missing range is the least fixpoint of interval analysis over the step,
starting from the initial value, widened to the program's constants (±1), then narrowed once. A variable
still growing at 2⁴⁰ is an error that asks for a saturating range. The analysis is sound but can
over-approximate; RR's `last` gets −1..2. The interval rules for `/` and `%` follow C semantics (12).

**36 — Locals are method-scoped.** A name is declared once per method, as the paper's `local x = e`
re-assignment form implies. Block scoping is rejected for that reason.

**5 — Buffer direction is inferred.** A parameter is an input if it is a `move-p` source, or if it
receives traffic or a connection; otherwise it is an output. Explicit `in` and `out` are optional.

**20 — Packet classes.** `packet { int<lo..hi> field; ... }` makes every combination of field values a
class, at most 4096 of them. A filter `B |> pred` over fields, constants and program variables is
allowed in move sources, `backlog-p`/`backlog-b`, `arrivals-p`/`drops-p` and traffic. Each buffer is
stored in one of two ways, chosen per buffer:
- **per-class counts**, when every move out of the buffer pins one class (its filter conjunction contains
  `field == e` for every field, with `e` free of fields);
- **a FIFO sequence** of class ids (slots and a length, unused slots 0) otherwise.

These are the URF's count and tuple buffer models. `--fifo-buffers` forces FIFO storage everywhere, and
the tests check that both representations agree. With classes, output buffers are always FIFO, which
costs no state. For the structured native step, the DAG keeps FIFO slot contents opaque (55).
*Rejected alternatives:*
- always FIFO: exact, but with far more states;
- multisets with a fixed tie-break: inexact.

**21 — `move-b(src, dst, n)`** moves the longest FIFO prefix of (matching) packets whose total size is at
most `n`. A head packet that does not fit blocks the rest; packets are never split. Sizes come from a
field named `size`; without one, every packet is 1 byte. `backlog-b` sums sizes.

**7 — Traffic observers.** `arrivals-p(b)` and `drops-p(b)` give the current step's arrivals and drops at
an input buffer. Monitors need them, for example to count enqueues as FPerf's `cenq` does. They are not
in the Buffy paper.

**6 — The `network` block** declares:
- `instance` and `capacity`;
- `traffic` (22, 37) and `phase` (37);
- `connect a.ob -> b.ib`, optionally `immediate` (11, 46);
- `init`;
- `horizon T`, which adds a saturating `time` variable (43);
- `assume` (26).

Queries (24, 25, 41), rewards (41) and importance hints (39) are declared at the top level.

## 3. Step semantics

**9 — Count buffers.** Without a `packet` declaration, a buffer is its packet count (the URF's tally
model). Input buffers tail-drop at their capacity, and output buffers start empty in every step. With
packet classes, see 20.

**10 — Queues.**
- `enq` on a full queue does nothing.
- `deq` on an empty queue returns `lo` and leaves the queue unchanged.
- Unused slots hold `lo`, so states are canonical.
- `deq()` must be the whole right-hand side of an assignment.

**11 — Composition.** A step has two phases: the arrivals, then every instance's program on the
post-arrival state. An output is flushed into its connected input at the end of the step, as in the
paper, so the downstream instance sees the packets in the next step. Connections are flushed in
declaration order. An `immediate` connection delivers within the step instead (46).

**46 — Immediate connections.** `connect a.ob -> b.ib immediate;` delivers what `a` puts into `ob` to
`b.ib` in the same step, after `b.ib`'s own arrivals and before `b`'s program, with tail drop. Instances
are elaborated in a topological order of the immediate connections; a cycle is an error, reported at a
connection. The network step stays one simultaneous update, so the JANI, PRISM and SMT-LIB backends
need no changes. For FPerf, see 45. The two kinds of connection coexist because a leaf-spine fabric
needs both: its links between switches deliver in the next step, and its stages within a switch in the
same step.

**12 — Out-of-range values are errors, not saturation**, matching the tools' behaviour. `--saturate`
clamps the globals. The FQ example saturates its monitors explicitly, because simulation and exact
exploration continue past the query horizon; `--stop-at-horizon` (43) is the other remedy.

Integer `/` truncates and `%` is C's remainder, in every target and in the constant folder. JANI and
PRISM spell this out, and use the target's own operator only when interval analysis proves both
operands non-negative.

**43 — `--stop-at-horizon`** freezes the state once `time` reaches the horizon `H`: every step update and
staged arrival update becomes `time < H ? update : current value`. Draws past `H` still happen, but they
return to the same state. The option changes the model's meaning beyond `H`, so it is opt-in, and every
query is checked against it:
- bounded `F`/`G`/`U` and monitor horizons must be at most `H`;
- `E` queries must be `C<=k` or `I=k` with `k ≤ H`.

The error is reported at the query.
*Rejected alternatives:*
- applying it automatically whenever every query qualifies: tools and users read the emitted model with
  other properties too;
- a separate sink state: it would lose the state at `H` that at-horizon queries read.

## 4. Randomness: traffic, phases and draws

**22 — Traffic with classes.** Each source selects exactly one class with a filter of constants, and a
buffer has at most one source per class. Several sources into one buffer arrive in declaration order
within a step, which decides tail drops. The elaborator, not the emitters, builds each staged arrival
transition's updates.

**37 — Phases and state-dependent distributions.** `phase x = init ~ D;` is a network-level state variable
redrawn from `D` in every step. `traffic b ~ c ? D1 : D2` makes a distribution depend on the state. A
phase is a source without a buffer, whose drawn value the step takes over (`Δ(x) = α_x`). Methods,
monitors and other sources therefore read its boundary value in every layout, and the scheduler's
information pattern is the same as for traffic.

**What boundary expressions may read.** A distribution's condition reads the state at the time-step
boundary: globals, monitors and phases. It may not read:
- buffers, whose value at that point differs between layouts;
- `arrivals-p`/`drops-p`, which are the draws themselves.

The same rule applies to network assumptions (26), which may also read the current step's
`arrivals-p`/`drops-p`.

Every branch must be probabilistic. JANI and PRISM receive probability expressions. SMT-LIB receives a
possibility condition per value. FPerf rejects phases.
*Rejected alternatives:*
- a dedicated `markov { ... }` source syntax, which is less general (no dependence on globals or other
  phases);
- random globals updated inside methods, which would break the deterministic step.

**44 — Draws inside methods: `x ~ D;`.** `D` is any traffic distribution: constant, conditional on the
instance's state at the boundary, or `nondet` (an MDP choice). Every occurrence, after loop unrolling, is
a source of its own (`Traffic::draw`, with no buffer and no state). It is drawn in every step, whether or
not the statement executes, and the statement assigns its value. The step stays a deterministic
function of the state and the step's draws, so the factored structure and every backend carry over:
- in JANI and PRISM, a draw is a bufferless source, like a phase without memory;
- in FPerf, it is a free value restricted to its possible values, which is FPerf's own nondeterminism.

Nondeterministic draws are resolved before the step's probabilistic ones, from the boundary state, as
nondeterministic traffic is. A draw gives the same model as `arrivals-p` of a capacity-0 buffer, in
every layout (`test/jani/same/`).
*Rejected alternative:* distributions that depend on values computed in the step. They would need
sequential sampling inside the step, which rules out the sync layout and breaks the deterministic step.
A draw over a fixed range, mapped onto the candidates, covers the common case.

**47 — Draw conditions may read loop variables.** `snd[i] ~ w[i] == 1 ? D1 : D2;` in a loop over `i` is one
state-dependent source per `i`. Conditions are resolved after elaboration, because they read the boundary
state rather than the step's values, and that happens outside the loop's scope. Each conditional draw
therefore records the loop variables in force where it is drawn, and restores them when its condition is
resolved. `examples/jani/outcast.buffy` uses this for TCP senders whose rate depends on their window.
`draws_loop.buffy` equals a hand-unrolled copy in every layout (`test/jani/same/`).

## 5. Queries and properties

**24 — Bounded LTL by compile-time monitors.** Queries are bounded LTL over state predicates (`F`, `G`, `X`,
`U` with step bounds; `! && || ->`). A single unnested `F`, `G` or `U` is encoded directly (15).
Everything else becomes a deterministic monitor, built at compile time by formula progression:
- negation normal form, with interned formulas;
- states enumerated by breadth-first search over the atom valuations;
- at most 16 atoms per state and 100,000 states.

The monitor's update reads the values the step computes, and the initial state is folded in at compile
time, so the monitor observes the time-step boundary states in every layout and in the native target.
The update selects the successor by binary search on the state index, so its depth is log₂ of the
number of states. The property is `F<=H mon = accept`. Monitors are used instead of a target's own LTL
because they work for every target, simulation included. PRISM-language LTL would serve Storm and PRISM
only, with no simulation in `modes`; this is question 3 of the JANI-vs-PRISM note.

**15 — `G` as the complement of `F`.** A `G` query is emitted as `<name>_violation` = `F ¬φ`, with min and max
swapped, in JANI, PRISM and SMT alike. Neither Storm nor `modes` accepts bounded `G` in JANI, and Storm's
PRISM parser has no bounded `G`.
*Open alternative:* emit a native `G` in PRISM files meant only for PRISM.

**38 — Minimised monitors.** Monitors are minimised by Moore partition refinement, whose signatures are
reduced ordered decision diagrams over the atoms. `true` is kept apart, so acceptance times are
preserved. Atoms are treated as independent inputs, which is sound but possibly incomplete.

**48 — Factored monitors.** A query whose top level, in negation normal form, is an and/or of temporal
subformulas may get one monitor per subformula, with the property `F<=depth (and/or of mon_i = accept_i)`.
This is exact because a bounded subformula's verdict is absorbing and the combination is positive.
Equal subformulas share a monitor, so a `given` condition is built once for `_joint` and `_given`.

Factoring is needed for conjunctions of time windows. Formula progression gives each conjunct its own
countdown, which duplicates `time`, so as one monitor two `F<=80` windows exceed the 100,000-state
limit; factored, they compile. The outcast study's learned conditions have this shape.

A single monitor is preferred while it stays under 20,000 states, because it is minimised as a whole.
`--factor-monitors` forces factoring, and `test/jani` checks every exactly checked example both ways.
*Rejected alternative:* time-anchored progression, which reads `time` instead of each `F<=b`'s own
countdown. It only helps formulas evaluated from a fixed position, and it needs to know that `time` is
monotone, which formula progression does not.

**41 — Rewards and expected values.** `reward r: e;` is earned once per time step, with `e` evaluated at
the end of the step: on the state after the step, with the step's own `arrivals-p`/`drops-p`. Queries
are `E{r}`/`Emax{r}`/`Emin{r}=? [ C<=k | I=k | F φ | S ]`.
- **No state.** Rewards are a transient JANI variable on the step edge, and a PRISM transition reward
  on `[step]`.
- **Bounds.** They are scaled by the transitions per time step. Long-run averages use the reward times
  that number, so `S` is per time step in every layout.
- **State reads** in a reward become placeholders, substituted by the updates, so `drops-p` keeps its
  in-step meaning.
- **SMT-LIB** skips expected-value queries.

Storm checks every form, in JANI and PRISM; `mcsta` checks only `F`.
*Rejected alternative:* monitor counters as reward proxies. They multiply the state space, cannot
express long-run averages or expected times, and per-threshold MDP optima only bound `Emax`.

**31 — Properties never mention step temporaries.** Properties are printed over state variables only, in
every target. A query atom can be the same DAG node as a step temporary, and temporaries exist only
during the step: Storm rejects a transient in a JANI property, and z3 rejects a step temporary in an
SMT-LIB query.

## 6. Assumptions, conditioning and rare events

**8 — `assume` and `assert` are sticky flags** (`inst.assume_violated`, `inst.assert_failed`), not pruning
or conditioning. Conditioning is expressed in the query (`given`, 25), applied exactly by
`--condition-on` (49), or approximated by pruning (27).

**26 — Network assumptions.** `assume e;` in the network block reads the boundary state (see 37) and the
current step's `arrivals-p`/`drops-p`. A violation sets the sticky `assume_violated`. With monitors for
memory, assumptions express path conditions on traffic, such as "no two successive steps without
arrivals" (`examples/jani/deck_rr.buffy`).

**25 — `given ψ`.**
- **DTMCs:** two properties, `<q>_joint` = P(φ ∧ ψ) and `<q>_given` = P(ψ), whose ratio is the
  conditional probability.
- **MDPs:** `Pmax` uses φ ∧ ψ and `Pmin` uses φ ∨ ¬ψ, so violating paths count against the optimiser.
  This is the constrained optimum when ψ only restricts nondeterministic choices and can always be
  respected.
- **`given assumptions`** means that no assumption flag is set within the formula's horizon.

*Rejected alternative:* Storm's conditional properties, which allow only reachability conditions and
only in Storm.

**27 — `--prune-violations`.** The violating step leads to one absorbing sink: all state except flags and
monitors returns to its initial values. It is off by default, because it makes queries that do not
exclude violations meaningless.

**49 — `--condition-on <query>`: exact conditioning of the input.** For a query's `given` condition ψ that
depends only on the random input:
- the compiler closes ψ's variables under their updates, giving the input cone;
- it computes `h_t(x)`, the probability that ψ will hold from cone state `x` at step `t`;
- it replaces the sources' probabilities by `p · h_{t+1} / h_t`.

The resulting path law is the original one conditioned on ψ (Doob's h-transform). Everything outside the
cone depends on the input only through its draws, so it is unchanged. P=? of the query's formula is
`P(φ | ψ)`, and `P(ψ) = h_0` is exact. This turns rare conditions, of probability 10⁻³ to 10⁻⁷ in the FQ
study, into ordinary simulation (`experiments/buffy_conditioning`).

**In JANI and PRISM**, `h` is a compile-time table:
- the compiler enumerates (step, cone state, ψ-monitor state) up to ψ's depth, at most 2·10⁶ states;
- `h` comes from backward induction;
- a new state variable `cond_<q>` selects the reweighted probabilities by a balanced lookup.

The cone must contain exactly one probabilistic source: each source has its own probabilities there,
and a joint reweighting does not factor into them. The native target computes `h` on demand (51) and
accepts several sources (52).

*Restrictions:* DTMCs only. A closed-loop input, whose distribution depends on state it does not drive
alone (as in the outcast study), is outside the cone and rejected.
*Rejected alternative:* importance weights in the simulator. They give unbiased but higher-variance
estimates; here the weights cancel exactly.

**51 — On-demand conditioning (native target).** The native target does not enumerate the cone at compile
time:
- it keeps ψ's monitor and a step counter as state variables, and emits the cone as a small C step
  function;
- the conditioned probabilities are `p · h(next) / h(current)`, where `h` is a memoised recursion over the
  cone states that runs reach;
- `condition_probability()` returns `P(ψ) = h(initial)` exactly.

The memory is bounded by the cone states visited, and the recursion depth is ψ's depth. On a PFC
condition, the compile-time table of 49 takes 50 s, 42 MB and minutes of clang. On demand, it compiles
in 0.14 s and builds in 1 s, and P(ψ) takes 0.01 s over 41,943 cone states. On `cond_input.buffy`, P(ψ)
matches Storm to rounding, and the conditional estimates fall in their 99.9% intervals
(`tests/test_native_conditioning.py`).

**52 — Joint conditioning on several sources (native target).** With conditioning on demand, the cone may
contain several probabilistic sources; it is closed as in 49.
- **One participant.** Conditioned on ψ, the sources are not independent: the reweighted joint law
  `p_1(x, a_1) ⋯ p_k(x, a_k) · h(x') / h(x)` does not factor. The emitter therefore makes them one
  participant of the step, whose outcomes are the sources' joint outcomes, with the first source varying
  fastest. The other sources stay separate participants, so the runtime needs no special case.
- **The memo.** `h` sums over joint outcomes. Its memo is capped by `BF_MAX_STATES` (default 20,000,000),
  and past the cap the process stops with an error rather than exhaust memory. The number of cone states
  grows exponentially with the number of sources a condition reads.
- **Checks.** On `cond_joint.buffy` (a condition on a sum of two sources, and a conjunction of conditions
  on each), P(ψ) matches Storm exactly. On the PFC model, a three-source condition memoises `h` over
  11 million cone states in about 25 s, and rejection over 4,000,000 runs agrees with a two-source
  condition's conditioned estimate (0.0246 against 0.0247).

**58 — Factored conditions (native target).** A condition ψ = ψ_1 ∧ … ∧ ψ_k often reads disjoint parts of the
input, each ψ_i its own sources and the state variables only those drive. The parts are then independent
Markov chains, and ψ_i is an event of part i alone. Conditioned on ψ they stay independent, each
conditioned on its own ψ_i: h(x) = ∏ h_i(x_i), each source is reweighted by its own part's h_i, and
P(ψ) = ∏ h_{i,0}.
- **Grouping.** The elaborator groups the conjuncts of a top-level ∧ into connected components by
  shared sources and shared random cone variables. A variable that no source drives, such as `time`, is
  the same function of the step in every part and may be shared. A conjunct without a source joins the
  first group. Each group gets its own monitor (`condm_<q>_<i>`), cone and depth (`Model::CondFactor`).
  The step counter is shared.
- **Emission.** Each group is one participant with its own memo. The per-group C names carry a suffix
  `_f<i>`. `bf_cond_p0` is the product over groups, and `bf_cond_states` the sum.
- **The joint case.** A condition that couples sources, or a single group, is emitted exactly as before.
  `--joint-condition` forces the joint form.
- **Checks.**
  - `cond_joint`'s `mixed` factors into two parts: P(ψ) matches Storm exactly, and the conditional
    estimate's interval contains the exact value. Its memo has 82 input states, against 307 jointly.
  - All other examples and variants are unchanged.
  - On the PFC model (`experiments/buffy_pfc/results/factored_memo.log` and `certify_factored.log`):

    | condition | memo, factored | memo, joint | h from the initial state, factored / joint |
    |---|---|---|---|
    | c1, culprit | 1,950 | 1,950 | same |
    | j1, culprit + V | 1,875 + 1,830 | 76,390 | < 0.01 s / 0.01 s |
    | t1, incast + culprit + V | 1,275 + 1,830 + 2,380 | 11,057,020 | < 0.01 s / 26 s |

    P(ψ) agrees to all 15 printed digits, and the conditioned estimates of P(Q | ψ) lie within each
    other's 95% intervals.

**39 — `--auto-importance`** derives an importance function per query: the progress of the target
predicate (comparison gaps from interval analysis; `&&` adds, `||` takes the best), refined for monitor
queries by the monitor's distance to acceptance. Its target value is reached exactly at the target
states, as `modes --ifun-prop` requires. Splitting stays unbiased whatever the function's quality.

## 7. JANI target and layouts

**13 — Layouts.**
- **`--layout auto`** (default): `sync`, or `choose` (30) for MDPs with more than 64 joint traffic choices
  per step.
- **`sync`** gives one JANI step per time step. It puts every instance in one `step` automaton,
  synchronised last, because Storm drops transitions when an edge with multi-level assignments is
  followed by another synchronising edge (Buffy `docs/jani-backend.md`). Per-instance structure survives
  in assignment comments.
- **`--staged`** gives 1 + S steps per time step, for S sources.
- **`--no-levels`** gives core JANI with a single update, for small programs; it is refused above
  2·10⁶ tree nodes.

**28 — Information pattern.** Staged layouts resolve nondeterministic sources before probabilistic ones,
keeping the per-buffer order. A scheduler therefore never sees the current step's probabilistic arrivals
before it chooses, as in the sync layout.

**30 (contains 40) — The `choose` layout for MDPs.** Each nondeterministic source chooses on its own edge
(`arr_<src>_<k>`, ordered by a `turn` variable), and that edge applies the source's arrivals. A register
holds the choice only when an earlier-declared probabilistic source precedes it into the same buffer,
because tail drops follow declaration order. One `tick` then runs the step with the probabilistic sources.
- **States.** The layout never has more states than a register for every source would (`rr`: 1,479
  against 4,320).
- **Bounds.** Property bounds are scaled by (choices + 1) and evaluated at `turn = 0`. A bound based on
  `time` was rejected, because it needs a `horizon`.
- **Speed.** On the FQ MDP, buffy-prism's JANI simulator takes 3.5 µs per time step in `sync` and 0.48 µs
  in `choose`.

**14 — MDP action names.** Every nondeterministic choice has its own action. The sync layout has one sync
vector per joint choice (`tick_k1_..`), and refuses more than 4096 joint choices. DTMCs use a single
`tick`.

## 8. PRISM target

**29 (contains 16) — Temporaries.** PRISM and stormpy expand formulas at parse time, so `--prism-temps auto`
picks formulas below 2·10⁶ tree nodes and `merged` temporary stages above that.
- **Merged stages.** Consecutive DAG levels are grouped while every inlined expression stays below 4096
  tree nodes (`--prism-stage-size`). Only temporaries read by a later stage are variables, and the last
  group is folded into `[step]`.
- **On FQ.** `merged` gives 11 PRISM steps per time step, against 46 for one stage per DAG level
  (`--prism-temps stages`). It has 104 bounded variables instead of 165, and a 460 KB file instead of
  32 KB.
- **Ranges.** PRISM's one-value ranges (`[0..0]`) are emitted one wider.

## 9. SMT-LIB target

**17 (contains 33) — Qualitative semantics.** Traffic is a symbolic workload over the distribution's
support, and a query asks "sat ⇔ some workload realises it" (⇔ Pmax > 0). Workload constraints are
network assumptions (26) with `given assumptions` (25), not extra syntax. Phases become possibility
conditions (37), and expected-value queries are skipped (41).

## 10. FPerf target

**18 — The DAG over FPerf's queue variables.** The FPerf backend evaluates the elaborated DAG directly over
FPerf's queue variables, instead of the URF's wp transformation with `$IN_*`/`$OUT_*` substitution.
Buffy's `traffic` is ignored: FPerf's workload drives the external inputs. Output packets come from the
recorded `move-p` events into outputs with one packet class, and from the output buffers' final contents
with several (45).

**45 (contains 32) — Multi-device networks.**
- **Modules.** Each instance is one queuing module, linked with FPerf queue edges as `connect` says.
  FPerf's queue semantics equal Buffy's flush: an output's enqueues land at the tail of the linked queue
  in the next step, tail-dropped at its size. Connected inputs use their value before the flush for
  `deq_cnt`. Modules share per-step state variables, and output queues are sized from their enqueues.
- **Packet classes** map to FPerf metadata (`meta1`, `meta2`, in field order) over FIFO storage, so at most
  two fields.
- **Program-filled buffers.** A buffer that a program fills itself is module state rather than an FPerf
  queue.
- **External inputs** can be same-step `IMM_QUEUE`s, which is Buffy's own order.
- **Immediate connections.** Instances joined by them form one module, whose immediately connected
  inputs are internal state. Reading FPerf's `IMM_QUEUE` there would count the same-step packets twice,
  because the DAG already appends them.
- **Equivalence checks.** `BuffyNet` builds the modules inside any contention point. `fperf_equiv_test`
  checks each hand-written FPerf contention point against its Buffy program for every workload up to a
  horizon, with pins for FPerf's nondeterministic choices and a refinement check for crossbars.

See `docs/notes/fperf-cps-in-buffy.md`.

## 11. Native target

**50 — A C model core instead of JANI.** Going through JANI would print the step DAG as JSON (42 MB for one
conditioned PFC model), which the simulator would parse and translate back to C, losing the sharing and
any structure Buffy knows. `--target native` writes a JANI header (variables, properties) with a C model
core under `x-buffy-native`. The core defines what `jani_native.JaniModel` would otherwise generate:
- the destination tables;
- `jm_enabled`;
- the step.

The simulator appends its generic runtime: sampling, goals, observables, policies, batch simulation and
splitting. The core has the sync layout's semantics:
- one edge per joint nondeterministic choice, with at most 4096;
- the probabilistic sources as parts, in traffic order.

With the same seed, a run is identical to the JANI sync layout's (`tests/test_native_target.py`, every
example). The simulator also reads JANI from other tools, and turns balanced selection trees in it into
lookup arrays; that is exact (`tests/test_native_tables.py`).

**54 — The structured step.** The program's step is C that follows the program (`src/lower/NativeStep.inc`,
`Model::NativeStep`):
- loops stay loops, and `if`s are tested at run time;
- each buffer is a contiguous array handled by generic helpers (`bf_count`, `bf_take`, `bf_append`),
  with the semantics of the symbolic `take` and `append`;
- queues and arrays are contiguous too, with select and update semantics for dynamic indices.

The state vector is that of the unrolled step, so properties, observables and conditioning carry over.
The updates outside the program are emitted as small DAG blocks: time, phases, LTL monitors, network
assumption flags and conditioning, plus rewards. Monitors and rewards read the new state through `post:x`
placeholders. Pruning and the stop at the horizon are applied in the elaborator's order.

The unrolled step, one C temporary per DAG node, is available as `--native-dag`. It is also used
automatically in two cases, after re-elaborating without the structured step:
- a program the generator does not support;
- a `--condition-on` condition that reads the order of packets in a FIFO buffer.

`tests/test_native_structured.py` compares the two on every example and variant: states, probabilities
and rewards of every enumerable destination. They are identical. On Loom (capacity 32, 16 cores), a run
costs 0.47 ms with the structured step and 31 ms with the unrolled one, and the build takes 0.6 s against
about 6 minutes.

**53 — Joint outcomes are not numbered.** A step can have more joint outcomes than an integer holds: Loom at
16 cores has 48 Bernoulli sources, so 2⁴⁸ outcomes.
- **Sampling.** The sampler records each participant's outcome as it draws it, and a core that defines
  `JM_APPLY_DD` (Buffy's native core) applies the step from those digits.
- **Exact enumeration.** The joint index is used only by `jm_ndest`, `jm_prob` and `successors`. It is
  0 when it does not fit, and `successors` then refuses.
- **The JANI translator.** Its cores number the joint outcome, and refuse a step whose index would
  overflow.

Both paths give identical runs, draw for draw (`tests/test_native_conditioning.py`,
`test_native_target.py`).

Conditioning on demand (51) and joint conditioning (52) are in section 6.

## 12. Elaboration cost and size limits

**55 — Elaboration in time linear in the model.**
- **`if` joins** cost O(locations written). Each branch logs its first write of each location, and the
  join visits only those. The enclosing branch logs them in turn. Copying the store at every `if` would
  cost O(#ifs × #locations), and every buffer slot is a location.
- **Dynamic indices** reach only the elements in the index's interval, from the declared ranges of state
  variables and draws: Loom's `ten[2*i + pick]` reaches 3 elements, not 2·NC. When the interval may
  leave the array, the out-of-range semantics are kept (read the last element, write nothing).
- **FIFO slot contents.** For the structured native step they are one opaque value per range, because
  rank selection in `take` and placement in `append` are quadratic in the capacity and nothing executes
  them. Lengths, accepted counts and drops are exact.

The Buffy JANI suite (Storm against reference values) and the native equivalence tests pass. Loom with
capacity 32 compiles at 256 cores (51,083 state variables) in 4.3 s and 0.7 GB, builds in 2.1 s, and a run
costs 7.6 ms. At 512 cores with capacity 64 the compile takes 15–28 s and 2 GB.

**56 — The interval map is extended, and opaque nodes are cached.** Two costs would be quadratic on models
with many draws, such as the leaf-spine fabric (`examples/jani/fabric.buffy`):
- **The interval map** for dynamic indices is built once per step and extended with each new source's,
  and each new opaque value's, range. Rebuilding it per source would cost O(#draws × #variables). The
  extension is exact, because a memoised interval involves only variables already in the map.
- **`opaque(lo, hi)`** returns one cached node per range.

Neither changes the output.

**57 — No step DAG for the native target.** The structured step (54) computes the program's updates
itself. From the method bodies it needs four things:
- the declarations reached;
- the draws, with their loop values;
- which branches and indices are constant;
- which locations each instance writes.

It does not need the values. So for `--target native` the method bodies, and the flushes of connections,
are elaborated in an abstract expression context (`Ctx::setAbstract`, `src/immut/Expr.cpp`):
- A value is a constant or an unknown. An integer unknown carries an interval; a boolean unknown carries
  nothing.
- Constants fold exactly as in the normal context. With an unknown operand, only the rules that hold for
  any value of that operand apply (`x && false`, `x * 0`, `ite(c, k, k)`), never identities between equal
  nodes such as `x - x`.
- State variables and draws are unknowns in their declared ranges. A dynamic index's interval is its
  abstract value, which replaces the interval map of 56.

The model's context still builds the step's drops (read by rewards), traffic distributions, queries,
monitors, rewards and the updates outside the methods. None of the program's own updates enters the
model, since the structured step produces them.

Two cases elaborate again with the DAG (`NeedDag`):
- a global without a declared range, whose range is inferred from its update (the interval fixpoint is
  not reimplemented);
- a `--condition-on` cone that contains a program-updated variable, because the backend evaluates its
  update for h (`cond_input`, `cond_joint`).

`--step-dag` forces the DAG. Checks:
- On all 254 compilations of the examples and option variants, the C, the exit codes and the messages
  are identical. In 20 outputs the properties differ only in the operand order of commutative
  operators, which follows node creation order.
- The fabric is identical at 1,024 and 2,048 hosts, and Loom's C is identical at 512 cores.
- The JANI, parser, elaboration and SMT suites pass, and so do the native structured, conditioning and
  precision tests.

Effect, as peak footprint on the 8 GB laptop (`experiments/buffy_fabric/results/compile_no_dag.jsonl`,
measured with `experiments/buffy_fabric/compile_no_dag.sh`):

| model | with the DAG | without |
|---|---|---|
| fabric, 1,024 hosts | 15 s, 1.8 GB | 4.9 s, 0.24 GB |
| fabric, 2,048 hosts | 87 s (42 s CPU), 4.7 GB | 16 s, 0.49 GB |
| fabric, 4,096 hosts | 21 min (4.5 min CPU), 18.6 GB, paging | 69 s, 0.94 GB |
| Loom, 512 cores, capacity 64 | 15 s, 2.2 GB | 4.7 s, 0.79 GB |

The constant cache in `Ctx::i`/`Ctx::b` and hash sets in the join log are part of the same change.

**The size limit.** Compile memory is now linear in the program. Compile time is not: the abstract
elaboration still visits every element a dynamic index can reach, to join its value. On the fabric the
reachable ranges grow with the topology, so the compile goes from 16 s at 2,048 hosts to 69 s at 4,096
(P7). After that come the C core's tables and clang (P2): at 4,096 hosts the C is 28 MB and builds in
113 s.

## 13. Validation and testing

**19 — Exact checks on toy models only.** SP, the RR MDP, the tandem composition and assume/assert are
checked exactly against independent Python references:
- every layout in Storm and `mcsta`, except reward forms other than `F`, which only Storm checks (41);
- SMT answers against Storm, where any z3 error fails the test.

FQ-size models are compared only by simulation (`modes`, `prism -sim`, and a direct Python Monte Carlo of
the paper's Figure 2), always under `timeout`. `examples/jani/arith.buffy` covers:
- negative `%` and `/`;
- range inference over them;
- a query atom shared with the step.

`test/elab` has the elaborator's error cases, and pruning is checked in every layout.

**42 — Case-study programs in the language as it is.** `incast.buffy` and `llm_sched.buffy` reproduce the
hand-written PRISM models of the incast and LLM batch-scheduler case studies exactly: every property to
10⁻¹⁵ on small configurations, and within simulation error at full size. The design gaps these programs
exposed are discussed in `experiments/buffy_case_studies/README.md`; `--stop-at-horizon` (43) and draws
(44) address two of them.

## 14. Planned techniques (not implemented)

These come from the scaling studies: Loom up to 512 cores (`docs/notes/sprt-loom-results.md`), and the
leaf-spine fabric up to 4,096 hosts (`docs/notes/case-study-fabric-scaling.md`). Their timings are one core
of an 8 GB laptop. The techniques are listed in the order in which each would raise the size limit of 57.

P1, skipping the unrolled DAG for the native target, is decision 57.

- **P7. Dynamic accesses at constant cost in the abstract elaboration.** An array or buffer array whose
  elements are all unknown in their declared ranges stays so under any dynamically indexed write. If such
  entities were marked, an access could skip visiting each reachable element, and compile time would
  follow the program.
- **P2. Compact tables in the C core.** Load and store contiguous state ranges rather than one entry per
  variable, and give draws in loops an affine source formula rather than a table. The fabric's C is 28 MB
  at 4,096 hosts, and clang takes 113 s on it.
- **P3. State in the work layout between steps**, so that a step costs what it changes rather than
  O(state).
- **P4. Strided or modular intervals for dynamic indices**, so that `x[(i + r) % N]` stays narrow for the
  JANI and PRISM targets, and cheaper to elaborate for the native one.
- **P5. Parallel runs** across cores in the native simulator (a runtime change).
- **P6. Compositional importance functions** that see the bottleneck's queues. Splitting with the derived
  function (39) gains only about 2.5× at P ≈ 6·10⁻⁶ on the fabric.

None of these addresses three limits that are inherent:
- exact checking of large models;
- exact conditioning on many sources jointly (52);
- guarantees over all inputs.

## 15. Index

| decision | section | | decision | section | | decision | section |
|---|---|---|---|---|---|---|---|
| 1 | 1 | | 20 | 2 | | 39 | 6 |
| 2 | 1 | | 21 | 2 | | 40 | 7 (in 30) |
| 3 | 1 | | 22 | 4 | | 41 | 5 |
| 4 | 2 | | 23 | 2 | | 42 | 13 |
| 5 | 2 | | 24 | 5 | | 43 | 3 |
| 6 | 2 | | 25 | 6 | | 44 | 4 |
| 7 | 2 | | 26 | 6 | | 45 | 10 |
| 8 | 6 | | 27 | 6 | | 46 | 3 |
| 9 | 3 | | 28 | 7 | | 47 | 4 |
| 10 | 3 | | 29 | 8 | | 48 | 5 |
| 11 | 3 | | 30 | 7 | | 49 | 6 |
| 12 | 3 | | 31 | 5 | | 50 | 11 |
| 13 | 7 | | 32 | 10 (in 45) | | 51 | 6 |
| 14 | 7 | | 33 | 9 (in 17) | | 52 | 6 |
| 15 | 5 | | 34 | 1 (in 1) | | 53 | 11 |
| 16 | 8 (in 29) | | 35 | 1 | | 54 | 11 |
| 17 | 9 | | 36 | 2 | | 55 | 12 |
| 18 | 10 | | 37 | 4 | | 56 | 12 |
| 19 | 13 | | 38 | 5 | | 57 | 12 |
| | | | | | | 58 | 6 |
| | | | | | | P2–P7 | 14 |
