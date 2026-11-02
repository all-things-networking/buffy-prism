# Buffy → MDP: the translation, why Buffy fits, and other front ends (2026-11-01)

The full formal account is `buffy/docs/compilation/buffy-compilation.pdf`. This note gives the
short version, compares Buffy with the NetKAT family and p4v, and reviews the related work of the
Buffy HotNets'24 paper and more recent work, to answer whether other front ends are worth
supporting.

## 1. The translation in one page

**What a Buffy program denotes.** One or more methods (schedulers, shapers, AQMs) over input and
output *buffers*, plus a `network` block: capacities, traffic sources, connections and assumptions.
Together they define a discrete-time system. In every **time step**:
1. traffic arrives (tail-dropped at capacity);
2. every method runs once on the post-arrival state;
3. connected outputs are flushed into their downstream inputs.

**The key structural fact.** All randomness and all nondeterminism is in the traffic sources (and
phases). The step itself is a deterministic function of the state and the arrivals. A Buffy program
is therefore a *factored* MDP:
- **state:** globals, monitors, input buffers, phases (bounded integers and Booleans);
- **actions:** the choices of the nondeterministic sources;
- **transitions:** the product of the probabilistic sources' distributions, followed by one
  deterministic update `Δ`.

**Pipeline.**

| stage | what happens |
|---|---|
| parse (ANTLR 4) | syntax AST |
| elaborate (symbolic execution of one step) | loops unrolled, arrays flattened, branches joined into `ite` nodes, buffers lowered to counts or FIFO slots; result: a hash-consed DSA DAG with one update per state variable |
| model (`Model`) | state variables with ranges (declared or inferred by interval analysis), sources (distributions, `nondet`, phases), updates, properties, rewards |
| layout | JANI `sync` (1 transition per step, temporaries as transient variables at assignment levels), `staged`, or `choose` (one decision per nondeterministic source); PRISM with formulas or merged temporary stages |
| queries | bounded LTL compiled to minimised deterministic monitors; `given` conditions; expected values (`C`, `I`, `F`, `S`); bounds scaled by transitions per step |

**What keeps the state space small:** no program counter (a method is one simultaneous update);
transient temporaries; per-class counts instead of FIFO sequences when no move can observe order;
canonical encodings; inferred ranges; minimised monitors; pruning of violating paths. All layouts
agree at time-step boundaries (checked on every example in Storm and mcsta).

## 2. Why Buffy is well suited to MDP translation

1. **Time is explicit and discrete.** Performance properties are statements about behaviour over
   time steps: backlog after k steps, starvation within T, long-run throughput. Buffy's semantics is a
   step function, which is exactly a transition of a discrete-time Markov model. Nothing needs to be
   invented to get a clock.
2. **Randomness lives at the boundary.** Because traffic (and phases) carry all the probability and
   nondeterminism, the compiled models have a clean information pattern: schedulers choose before the
   step's random arrivals are drawn. Workloads, adversaries and policies are first-class objects
   (actions named `arr_<source>_<k>`), which is what MDP analysis and RL need.
3. **Buffers are first-class, so abstractions can be chosen.** The language talks about moving
   packets between buffers, not about packet histories, so the compiler can choose the
   representation: counts, per-class counts or FIFO sequences, by a sound static analysis.
   The same insight drives the NSDI'26 follow-up on count-based buffer abstractions
   (counts plus windows) for SMT verification.
4. **Everything is finite by construction.** Constant loop bounds, bounded arrays and ranged
   integers (paper §7, "Discussion") are what an explicit-state or simulation backend needs.
   They aren't limitations to work around.
5. **Queries are part of the program.** Monitors, `assume`/`assert`, bounded LTL, conditions and
   rewards are written in the same language as the model, and compile to state the backends
   understand.
6. **One front end, several back ends.** The same IR drives SMT-LIB and FPerf (qualitative,
   workload synthesis) and JANI/PRISM (quantitative). A result can be cross-checked across
   reasoning styles: SMT `sat` ⇔ `Pmax > 0` is a regression test.

## 3. How the NetKAT family differs

NetKAT (Anderson et al., POPL'14) and its descendants
model a network as a function from a packet to packets (or packet histories), built from tests,
field modifications, union, sequencing and iteration over the topology.

| aspect | NetKAT family | Buffy |
|---|---|---|
| unit of analysis | one packet's journey (or a distribution over journeys) | the joint state of all buffers, over time |
| interaction between packets | none: each packet is processed independently | essential: packets contend for buffers and links, and schedulers decide who goes |
| time | none (hops, not steps) | discrete time steps |
| mutable state | none in the core calculus (switch state is configuration) | globals, queues, monitors updated every step |
| probability | ProbNetKAT (Foster et al., ESOP'16): random choice per packet (failures, randomised routing) | traffic and phases; the step is deterministic |
| typical questions | reachability, loop freedom, equivalence, delivery probability under failures | starvation, backlog, losses, fairness, worst-case workloads |
| decision method | KAT automata and equivalence; Markov chains per packet | MDP/DTMC model checking, simulation, SMT |

**McNetKAT** ([Smolka et al., PLDI'19](https://arxiv.org/abs/1904.08096)) shows how far the
per-packet view scales. Its guarded, history-free fragment of ProbNetKAT is interpreted as
finite absorbing Markov chains, and it handles networks with thousands of switches, because a
single packet's state is small. That same view is the reason it cannot express a scheduler. A
scheduler's behaviour *is* the interaction of packets in a buffer, and the per-packet semantics
abstracts exactly that away. Weighted NetKAT (WNetKAT, cited in the Buffy paper) adds costs on
paths, still per packet.

**Bayonet** ([Gehr et al., PLDI'18](https://pldi18.sigplan.org/details/pldi-2018-papers/9/Bayonet-Probabilistic-Inference-for-Networks))
is the closest relative. It is a probabilistic network language with switch queues, analysed by
translation to general probabilistic inference, and evaluated on congestion and delivery
reliability for topologies of up to about 30 nodes. The differences: it targets exact Bayesian
inference (conditioning) over small networks, and its scheduling of queues is a
fixed resolution rather than a program. Buffy makes the scheduler the program, adds
nondeterministic workloads (MDPs), and relies on state-space reduction and simulation to reach
FQ-sized models.

**ProbNV and NetDice** ([ProbNV, ICFP'21](https://www.cs.princeton.edu/~dpw/papers/probnv-2021.pdf);
[NetDice, SIGCOMM'20](https://www.doi.org/10.1145/3387514.3405900)) are probabilistic
*control-plane* verifiers: the probability that routing configurations (BGP, OSPF) meet a property
under random link failures. They answer a different question, which forwarding state arises, rather
than how traffic performs given that state.

## 4. How p4v differs

p4v ([Liu et al., SIGCOMM'18](https://www.cs.cornell.edu/~liujed/papers/p4v-sigcomm2018.pdf))
verifies P4 programs, the parsers and match-action pipelines of programmable switches, against
safety properties such as header validity, using weakest preconditions, SMT and hand-written
control-plane assumptions. The differences are fundamental, not just of degree:

- **The part Buffy models is outside P4.** P4 programs the per-packet pipeline. The queues and the
  scheduler (the traffic manager) are fixed-function blocks between the ingress and egress
  pipelines, so a P4 program has nothing to say about contention, queueing or scheduling.
- **Per packet, no time.** p4v reasons about one packet's traversal (registers aside), with no notion
  of a sequence of time steps or of other packets.
- **Safety, not performance.** Its properties are assertions over a single traversal: no
  probabilities, rates or workloads.

Lucid ([Sonchack et al., SIGCOMM'21](https://arxiv.org/abs/2107.02244)), an event-driven data-plane
language compiled to P4, moves closer: it has persistent state and events, with verification support
added recently (VeriLucid, SIGCOMM'26). It still targets the programmable pipeline, not the
traffic manager.

## 5. The paper's case studies and related work, and what has happened since

**Case studies (§6 of the HotNets version): FPerf and CCAC.**
- FPerf ([NSDI'23](https://www.usenix.org/conference/nsdi23/presentation/tahmasbi)) is SMT
  verification of contention points with workload synthesis. Buffy now compiles to it directly
  (multi-instance contention points, checked against hand-written FPerf models) and to SMT-LIB.
  The probabilistic path covers the same FQ scheduler quantitatively.
- CCAC models congestion control over a non-deterministic token-bucket "path server" plus a fixed
  delay. Its components are expressible in Buffy as separate instances connected by buffers (the
  paper's Figure 7). Rendered as an MDP, the path server's nondeterminism becomes actions, which
  would give quantitative questions (loss probability under random cross-traffic) next to CCAC's
  worst-case ones. This is not built yet.
- Dafny was the paper's manual back end. The compiler replaces the manual transformations
  (unrolling, inlining, flattening) with automatic ones.

**Related work (§8):** FPerf and CCAC, quantitative network analysis, probabilistic reasoning
(ProbNetKAT, Bayonet), language frameworks (NetKAT, NV, Batfish, Zen), PIFO trees, and verification
back ends (Z3, Dafny, Spacer, SyGuS). Developments since that are relevant:
- **Count-based buffer abstractions** ([Seyhani et al., NSDI'26](https://www.usenix.org/system/files/nsdi26-seyhani.pdf)):
  buffers as counts, plus windows to recover ordering constraints, to scale FPerf-style
  verification to buffers of hundreds of packets. Its buffer interface is designed to align with
  Buffy. Our compiler's count/FIFO choice is the exact (no over-approximation) special case. The
  windows idea is a candidate for a controlled over-approximation in the MDP path too.
- **Formal semantics of PIFO trees** ([Mohan et al., OOPSLA'23](https://arxiv.org/abs/2211.11659)):
  operational semantics and compilation between PIFO-tree topologies. PIFO trees are how schedulers
  are specified in the programmable-scheduling literature.
- **Exact discrete probabilistic programming** (Dice and successors such as Roulette): exact inference
  by knowledge compilation; see section 6.

## 6. Dice (and exact probabilistic programming) revisited

Dice ([Holtzen et al., OOPSLA'20](https://arxiv.org/abs/2005.09089)) is a first-order discrete
probabilistic language with exact inference by compilation to binary decision diagrams (weighted
model counting). The URF report (Fall 2024, chapter 4) translated Buffy programs to Dice and PERPL
by hand (formerly `examples/ppl/` in the Buffy repository). It ran into three obstacles:

1. **Buffers as lists.** Buffers were Dice lists manipulated by recursive helpers (`enq`, `append`,
   `take`), but Dice supports recursion only unofficially, with a list-length cap, and compile times
   grew quickly for medium examples.
2. **Fixed-width unsigned integers and constant distribution parameters.** Every integer had to be
   given a bit width by hand, and distributions could not depend on the state.
3. **No nondeterminism.** FPerf's questions are existential over workloads ("is there a workload
   such that ..."), and Dice is purely probabilistic. That is why usable Dice versions of FPerf's
   examples did not emerge: there is no Dice counterpart of an FPerf query unless the workload is
   first given a distribution.

The compiler removes the first two obstacles. After elaboration, a program is a set of bounded
integer state variables updated by a shared expression DAG, with buffers already lowered to counts or
FIFO slots: no lists, no recursion. A Dice back end would map:
- each state variable to an `int(w)` holding `x - lo`, with the width w taken from the
  (declared or inferred) range;
- shared DAG nodes to `let` bindings, which preserves the sharing;
- each source to a `discrete(...)`, and state-dependent distributions to `if` expressions over them;
- the T time steps to an unrolling;
- queries to the Boolean returned, and `given` to `observe`.

Arithmetic needs care, because Dice integers are unsigned and wrap around. Intermediate results
need widths from the interval analysis, which the compiler already computes.

**What Dice could add:**
- **Exact conditioning** (`observe`), including inverse questions such as "the probability that a
  source was in its ON phase, given that flow 2 lost packets". The model checkers express
  conditioning only as a ratio of two properties, and not at all for MDPs.
- **Full output distributions in one inference:** the exact distribution of total loss or final
  backlog, which gives exact tails and CVaR as ground truth for case study 4 on small instances.
- **A second, independent exact engine** next to Storm.

**What it cannot do:**
- MDPs (there's no nondeterminism), so no worst-case workloads; and no long-run averages.
- Scale. Unrolling T steps of a queue model with coupled integer counters is unlikely to compete
  with model checking, which exploits the Markov structure: it explores each reachable state once,
  while Dice compiles whole computations.

**Newer work building on Dice**, and what each would mean here:

| work | what it adds | relevance to Buffy |
|---|---|---|
| noDice ([Gürtler and Kaminski, OOPSLA'26](https://arxiv.org/abs/2602.20049)) | nondeterminism **and** conditioning for loop-free Dice programs, by building an MDP whose schedulers correspond to the program's distributions; decision diagrams shrink that MDP | the most relevant: T unrolled steps are loop-free, so it could give exact optima over workloads *with* conditioning (`given` for MDPs, which the model-checking path only approximates); small instances only, since unrolling exposes every step |
| Scaling integer arithmetic ([Cao et al., UAI'23](https://arxiv.org/abs/2307.13837), Dice.jl) | binary encodings that exploit the structure of sums and comparisons | the main scaling obstacle for a Buffy back end (buffer counts, sums, comparisons); would make a Dice back end viable on larger toy models |
| Unbounded iteration ([Torres-Ruiz et al., FSCD'24](https://drops.dagstuhl.de/storage/00lipics/lipics-vol299-fscd2024/LIPIcs.FSCD.2024.20/LIPIcs.FSCD.2024.20.pdf)) | exact stationary distributions in a Dice-style language | long-run averages; Storm already provides these for our models |
| Loaded Dice (OOPSLA'25) | exact gradients through Dice's compilation | gradient-based tuning of distribution parameters, e.g. searching parameterised (`once`) workload families for the worst case |
| dappl ([Cho et al., 2025](https://arxiv.org/abs/2502.18728)) | maximum expected utility with rewards and decisions, by compilation | single-stage decisions; not sequential MDPs, so little direct use |
| Roulette ([Moy et al., PLDI'25](https://pldi25.sigplan.org/details/pldi-2025-papers/85/Roulette-A-Language-for-Expressive-Exact-and-Efficient-Discrete-Probabilistic-Prog)) | exact inference for a large subset of Racket | expressiveness rather than scale or MDPs |

None of these changes the scalable path for MDPs, which remains model checking on small instances and
simulation with learned schedulers on large ones. noDice would fill a specific gap: exact optima
under conditioning.

**Verdict:** a possible *back end*, not a front end. It's small to build now (on the order of the
PRISM emitter) and worth a measured prototype on the toy examples, mainly for exact conditioning and
full distributions. PERPL ([Chiang et al., OOPSLA'23](https://doi.org/10.1145/3586050)), which
handles recursion exactly, is no longer needed for Buffy: the compiled models have no recursion
left. Low priority until a case study needs exact conditioning.

## 7. Should we support other front ends?

Not as replacements. Buffy's abstractions (time steps, buffers, workloads, queries) match the
problem, and the alternatives either lack contention and time (NetKAT, p4v) or target a different
layer (control plane, data-plane pipeline). Three *additions* would pay off, in order of value:

1. **A PIFO-tree front end.** Compile PIFO-tree scheduler specifications, with the OOPSLA'23
   semantics, to Buffy methods. Many published schedulers are given this way, so it would bring a
   corpus of real schedulers into the MDP, SMT and FPerf paths at once. Buffy's buffers and moves are
   the natural target; ranks would need a small extension (priority-ordered buffers).
2. **Component libraries rather than languages.** CCAC's path server, token buckets, delay lines,
   AQMs (CoDel, RED), and traffic models (ON/OFF and other Markov-modulated sources, now expressible
   with phases), packaged as reusable Buffy instances. This covers most "other front end" needs
   without a new parser.
3. **An importer for Bayonet-style programs** (optional), for benchmark comparison on the small
   networks Bayonet handles. It is useful as a cross-check, not as a modelling language.

Not recommended:
- **P4 or Lucid as front ends.** The per-packet pipeline logic they describe (classification,
  marking) could be extracted into Buffy method bodies, but the part performance depends on, the
  scheduler, is absent from P4.
- **NetKAT as a front end.** Its value is per-packet forwarding at scale. It could at most supply
  routing (which buffer a flow enters) as a preprocessing step.
- **Probabilistic programming languages as front ends.** They are general but don't know about time
  steps or buffers; every model would re-encode Buffy's semantics by hand, which is what Buffy exists
  to avoid. As back ends they are a different matter (section 6).

**Gaps in Buffy itself that a front end would not fix:**
- per-packet latency (needs timestamps per FIFO slot);
- loops with non-constant bounds;
- continuous time (CTMCs) for queueing-theory comparisons;
- oblivious adversaries (fixed workloads; noted in the design decisions).

These are language and compiler extensions, and they matter more than additional front ends.
