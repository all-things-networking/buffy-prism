# FPerf's queuing modules and contention points in Buffy

FPerf ships hand-written queuing modules (`fperf/src/qms`) composed into contention points
(`fperf/src/cps`): strict priority, round robin, a token bucket, the buggy two-level round robin
of the Buffy paper, Loom's NIC pipeline, and a leaf-spine fabric. Each now has a Buffy program in
`buffy/examples/fperf/`. Each program is compiled by Buffy's FPerf backend and compared with
FPerf's own network.

## How the comparison works

`buffy/test/fperf/fperf_equiv_test.cpp` puts the two networks side by side in one FPerf contention
point, sharing one Z3 context. The networks are FPerf's (wiring copied from the CP's `add_nodes` and
`add_edges`) and the Buffy program's (the same backend that `BuffyCP` uses). The external input
queues of both are constrained to receive the same packets at every step. Z3 is then asked for a
step at which a paired input's `deq_cnt`, or a packet enqueued to a paired output, differs.

- **UNSAT:** the two are equivalent for every workload up to the horizon T. This is stronger than
  agreeing on a set of queries: every FPerf metric over these queues is a function of the same
  enqueues and dequeues.
- **SAT:** the harness prints the first differing step with each queue's packets (`meta1/meta2`).

Some hand-written modules are nondeterministic: their constraints admit several behaviours for one
input. For those, a *pin* restricts FPerf to the choice the Buffy program makes, and the check is
repeated. For the leaf-spine crossbars, the pin could make FPerf unsatisfiable for some inputs,
which would make the check vacuous. So a third check withholds FPerf's matching conditions and asks
whether, with the pin, they can ever be violated. UNSAT there means the Buffy behaviour is always
one of FPerf's: Buffy *refines* FPerf.

## Results

| FPerf CP | Buffy program | result |
|---|---|---|
| `PrioScheduler` (4 queues) | `sp_prio.buffy` | equivalent, T=8 (9 s) |
| `RRScheduler` (5 queues) | `rr.buffy` | equivalent, T=8 (145 s) |
| `TBF` (rate 3, 6 tokens) | `tbf.buffy` | equivalent, T=6 (2 s) |
| `Buggy2LRRScheduler` (5 queues) | `fq_2lrr.buffy` | differs (FPerf's order of queues activated together is free); with index order pinned: **equivalent**, T=5 (21 s) and T=6 (138 s) |
| `Buggy2LRRScheduler` | `fq_paper.buffy`, the paper's scheduler | differs, as expected: see finding 2 |
| `LoomMQPrio` (4 cores) | `loom.buffy` (one method), `loom_modular.buffy` (one instance per FPerf module, `connect ... immediate`; the same at T=2) | differs (FPerf's flow enqueue may drop packets); with those drops forbidden: **equivalent**, T=2 (63 s) and T=3 (871 s) |
| `LeafSpine` (3 leaves, 2 spines) | `leaf_spine.buffy` | equivalent unpinned at T=3; pinned to Buffy's matchings: equivalent (186 s); Buffy's Gale–Shapley matchings **always satisfy** FPerf's matching conditions (236 s), so the Buffy fabric refines FPerf's. With `XBAR = 1` (any stable matching) it is **the same relation as FPerf's**, both directions at T=3. `XBAR = 2` (output-proposing) also always satisfies FPerf's conditions |

## Findings

1. **Buffy can express all six.** It needs packet classes for metadata, internal buffers, and, in
   two cases, one method per device because FPerf composes some modules within a step (finding 4).
   Two programs differ from a naive transcription in ways the comparison forced:
   - `fq_2lrr.buffy` defers the end-of-step bookkeeping of step t to the start of step t+1
     (finding 2);
   - the leaf-spine crossbar computes one particular stable matching (finding 3).

2. **FPerf's 2-level round robin looks ahead.** It decides whether the queue it served goes back to
   the old list, or which inactive queues join the new list, from the packets *enqueued during the
   step* (`enqs(0)[t]`). A causal step only sees those at t+1. The Buffy paper's scheduler decides
   from what it sees at t, so it is a different scheduler. The difference is concrete: a queue that
   empties and gets a packet in the same step goes to the old list in FPerf and to the new list in
   the paper's version, and the counterexample is found in about 5 s. `fq_2lrr.buffy` reproduces
   FPerf exactly by finishing step t's list updates at the start of t+1. Conclusions drawn with one
   model do not carry over to the other without this caveat.

3. **Several FPerf modules are nondeterministic, which looks unintended in two places:**
   - **2LRR:** queues activated in the same step may enter the new list in any order (the insertion
     constraints admit permutations).
   - **Loom flow enqueue:** the dequeue counts of tenant 2's flows are only bounded from below, so
     when more than `MAX_ENQ` tenant-2 packets wait, FPerf may silently drop the leftover ones.
   - **Crossbars:** the leaf-spine crossbars are specified as "a matching stable for the round-robin
     priorities". More than one stable matching can exist, and FPerf may pick any. The Buffy
     crossbar computes the input-proposing Gale–Shapley matching.

   An EXISTS query over a nondeterministic module is answered for the best choice, and a FORALL
   query for the worst. That is a hidden adversary which a probabilistic tool would want either
   resolved or made explicit as an MDP choice.

4. **Same-step composition.** FPerf's `IMM_QUEUE` edges let one module's output be processed by the
   next module in the same step: all of Loom, and forwarding into the crossbar inside a leaf-spine
   switch. Buffy instances run simultaneously and a `connect` delivers at the next step, which is
   FPerf's `QUEUE`/`LINK` semantics. The programs therefore put same-step pipelines inside one method
   (Loom; a switch's forwarding and crossbar), and use instances and `connect` between devices
   (leaves and spines). A `connect ... immediate` with a topological order of instances would let
   such pipelines stay modular; it would need the elaborator to run instances in that order.

5. **FPerf configuration quirks.** `RRScheduler` and `Buggy2LRRScheduler` leave `QueueInfo::type`
   uninitialised (undefined behaviour; the harness sets `QUEUE`). FPerf requires `max_enq` ≤ the
   queue size and indexes past the end otherwise. Buffy's backend now clamps the enqueues of its
   capacity-1 links (it crashed on the leaf-spine before the clamp).

6. **The refinement check found a bug in a Buffy program.** The first leaf-spine crossbar computed
   a rank as `(position − head − 1 + 2·LP) % n`. The offset must be a multiple of the list length
   n, and for the 3-VOQ server ports it was not, so their round-robin order was rotated. Pinned
   equivalence still held, because FPerf followed Buffy's choices. The withheld-conditions check
   showed that those choices were not stable for FPerf's priorities (at T=4, in leaf 2's crossbar
   at step 2). The fixed program passes at T=3. A pin alone can hide such errors; the third check
   is what catches them.

7. **Compiler bugs found on the way, fixed:**
   - Comparisons over FIFO slots with packet classes were built in exponential time: `Ctx::eq`
     folded into the branches of shared `ite` DAGs without memoisation. Loom did not compile within
     10 minutes; it now compiles in 0.3 s. This affects every backend.
   - Two examples from the previous push (`incast`, `llm_sched`) had no parser golden files, so
     `make test-parser` failed on Buffy `main`.

## Random and nondeterministic choices inside methods

Exposing FPerf's free choices probabilistically, or as MDP choices, needed randomness inside a
method. Buffy now has `x ~ D;` (user guide §2.9.2, design decision 44). `D` is any traffic
distribution: constant, conditional on the instance's state at the time-step boundary, or
`nondet`. Every draw is a source of its own, so the step stays deterministic and every backend
applies.

- **JANI and PRISM.** `examples/jani/draws.buffy` (a state-dependent service distribution) and
  `draws_mdp.buffy` (a scheduler choice plus a random outage) give exactly the values of the same
  programs written with capacity-0 traffic sources. This holds in every layout: sync, staged,
  choose and PRISM. Both pairs are in the JANI test suite.
- **FPerf.** A draw is a free value restricted to its possible values. A server that serves only
  when `k ~ nondet(0, 1)` says so can be blocked for every step (SAT); with `k ~ {1: 1}` it cannot
  (UNSAT).

## First probabilistic result: ECMP collisions in the leaf-spine fabric

`leaf_spine.buffy` has a constant `ECMP` that selects how a leaf picks the spine for a packet bound
to another leaf:
- 0: the packet's field, FPerf's model, where the workload chooses it;
- 1: a uniform draw per packet;
- 2: a uniform draw per flow, at time 0.

The traffic is FPerf's bandwidth example made probabilistic. Every server sends to a distinct server
on another leaf (server 0 to server 5), one packet per step with probability λ. `starved` is FPerf's
query: flow 0 gets at most 4 packets in 10 steps.

Native simulator (`src/netmdp/sim`), 100,000 runs each (95% CI half-width ≤ 0.003):

| spine choice | λ = 1 | λ = 0.5 |
|---|---|---|
| packet field, all on spine 0 (FPerf's adversarial worst case) | 1.000 | 0.987 |
| random per packet | 0.143 | 0.771 |
| random per flow | 0.750 | 0.852 |

- **Per-flow ECMP.** At λ = 1 the result is the collision probability. Flow 0 is starved exactly
  when flow 1 (sharing its leaf's uplink) or flow 2 (sharing the spine's downlink to leaf 2) hashes
  to its spine: 1 − ½·½ = 3/4.
- **Per-packet spraying** removes most of that risk.
- **FPerf** can only report that some hash assignment starves the flow.
- **λ = 0.5.** "At most 4 packets" is likely even without contention, since the flow offers about
  5 packets in 10 steps over a 3-step path. A load-normalised query (delivered vs offered) is
  needed below saturation.
- **Speed.** The model has 647 state variables and 6,147 transients per step. The native simulator
  takes about 0.3 ms per run (30 µs per step, after 20–50 s of compilation). `modes` did not
  finish 2,000 runs in 10 minutes. Reduced fabrics and an `argmin`/`argmax` builtin are therefore
  not needed for these runs; the builtin would still shrink the crossbar's DAG.

## Same-step composition: `connect ... immediate`

Finding 4 is now addressed. `connect a.ob -> b.ib immediate;` delivers within the step (user guide
§2.9.3, design decision 46). `loom_modular.buffy` builds Loom as FPerf does, with one instance per
module, and it is as equivalent to FPerf's network as the one-method program. In FPerf, instances
joined by immediate connections become one module.

## Matching FPerf's crossbar exactly

With draws inside methods, the crossbar no longer has to be deterministic. With `XBAR = 1` every VOQ
gets a nondeterministic candidate bit. The candidate is used when it is a matching on non-empty VOQs
in which every unmatched non-empty VOQ ranks below a matched one at its input or its output (FPerf's
conditions); otherwise Gale–Shapley's matching is used. That is exactly FPerf's set of stable
matchings. The harness proves it in both directions at T=3:
- every Buffy choice satisfies FPerf's withheld matching conditions;
- with Buffy's candidates pinned to FPerf's matching, Buffy always ends up with exactly that matching.

`XBAR = 0` and `XBAR = 2` are the input- and output-proposing Gale–Shapley matchings, the two extremes
of the stable matchings, and both refine FPerf.

## More probabilistic results

**Leaf-spine throughput.** Expected packets of flow 0 delivered by step 10 (the pipeline allows at
most 7), against offered load; native simulator, 50,000 runs per point:

| λ (offered by T) | fixed spine | per-flow hash | per-packet hash |
|---|---|---|---|
| 0.25 (2.5) | 1.84 | 1.93 | 1.93 |
| 0.5 (5.0) | 2.90 | 3.43 | 3.60 |
| 0.75 (7.5) | 3.19 | 4.31 | 4.69 |
| 1 (10) | 3.00 | 4.88 | 5.29 |

The hash policy is irrelevant at light load. From λ = 0.5 up, a fixed spine loses a third to half of
the throughput; per-flow hashing recovers most of it and per-packet spraying the most.

**Does the crossbar's choice of matching matter?** The input- and output-proposing matchings, the
two extremes of the stable matchings, give identical estimates (same seeds, 50,000 runs) for
per-packet and per-flow ECMP at λ = 0.75 and 1 (`results/xbar.log`): starvation 0.405 / 0.144 /
0.742 / 0.750 and the same throughput. The models differ, so configurations with more than one stable
matching are too rare under this traffic to show at this precision. Each server injects at most one
packet per step, so a port rarely holds two non-empty VOQs that two outputs both want in a cycle.
For this workload FPerf's freedom of choice in the crossbar is irrelevant. Workloads with more
contending flows per port would test it.

**Loom isolation.** P[tenant 2 leads by more than 3 packets at every step 6..9], FPerf's query, over
the tenants' and memcached's per-flow loads (50,000 runs each):

| L1 | L2 | LM = 0 | LM = 0.1 | LM = 0.25 |
|---|---|---|---|---|
| 0.5 | 0.5 | 0.006 | 0.073 | 0.347 |
| 0.5 | 1 | 0.069 | 0.143 | 0.290 |
| 0.25 | 0.5 | 0.163 | 0.399 | 0.742 |
| 0.1 | 0.5 | 0.645 | 0.809 | 0.948 |

With equal tenant loads isolation almost always holds. A memcached load of 0.1 per flow (0.4 packets
per step in all) already raises the violation twelvefold, and 0.25 makes it about one in three;
tenant 1's deliveries fall from 5.25 to 2.36. This is a mild input under which the bad behaviour
is likely. Memcached has strict priority at the NIC but counts towards tenant 2, and FPerf's
workload kept it idle.

**Priority starvation** (`examples/jani/prio_load.buffy`, exact with Storm, 4,320 states).
P[queue 2 blocked in more than 5 of 7 steps], FPerf's query, against the load LH of each of the two
higher-priority queues (L2 = 0.5, L3 = 0.3):

| LH | 0.2 | 0.3 | 0.4 | 0.5 | 0.6 | 0.7 | 0.8 |
|---|---|---|---|---|---|---|---|
| P[starve] | 0.017 | 0.093 | 0.248 | 0.436 | 0.592 | 0.687 | 0.731 |

The transition is gradual through saturation (2·LH = 1 at LH = 0.5), not a threshold. It stays
below 1 because queue 2 is blocked only while it has packets.

Scripts: `experiments/buffy_fperf/run_ecmp_load.sh`, `run_loom.sh`, `run_xbar.sh`, and
`native_eval.py`, which evaluates every bounded probability and C/I expected value of a Buffy JANI
file with the native simulator.

## Probabilistic checks for the same examples (the original brainstorm)

FPerf answers "is there a workload, among those satisfying a spec, under which the query holds?"
and synthesises workload specs, which are conjunctions of bounds on cumulative enqueues, under
which the query holds for every trace. Each example has a probabilistic counterpart that says how
*likely* the bad behaviour is under a model of the input. The counterpart also says which
conditions on the input make it likely. That is the conditional reasoning of the case studies
(`docs/notes/case-study-proposals.md`). All of the following compile from the same Buffy programs to
JANI and PRISM; only the `traffic` declarations are new.

**The general recipe.**
- `P[Q | spec]` for FPerf's synthesised spec is 1 by construction (FORALL), but `P[spec]` says how
  common the spec is under realistic arrivals, and `P[Q | ¬spec]` how much of Q the spec explains.
- A spec with small `P[spec]` that explains most of Q is a sharp diagnosis; a spec with large
  `P[spec]` and moderate `P[Q | spec]` is the mild-but-dangerous condition the case studies look for.
- FPerf's nondeterministic choices (finding 3) become MDP choices, and `Pmax`/`Pmin` bracket how much
  the unresolved choice matters.

**Per example:**

1. **Strict priority (FPerf: queue 2 blocked more than 5 steps).**
   - `P[cblocked₂ > k within T]` as a function of the higher queues' load λ₀ + λ₁, Bernoulli or
     ON/OFF (phase) arrivals.
   - The long-run fraction of time blocked, `E{blocked}=? [S]`, which FPerf's counts cannot
     express.
   - A threshold in λ₀ + λ₁ where starvation goes from rare to certain. The case-study pattern
     suggests it is sharp in load and gradual in burstiness.
2. **Round robin (FPerf: queue 2 dequeues ≥ 3 more than queue 1 over the last period while queue 1
   was offered more).** Under random arrivals this unfairness should be rare. The interesting output
   is the conditional `P[unfair | queue 1 offered more]` and which arrival correlation (bursty
   queue 2, synchronised periods) raises it. FPerf's periodic spec (`cenq ≥ i·rate` at period ends)
   is one point of that space.
3. **2LRR / FQ-CoDel (FPerf: the last queue's cumulative dequeues reach (T/5)+3).**
   - This is the FQ case study; the new angle is the two timings of finding 2. Compute
     `P[deqs_bl ≥ 4]` for `fq_paper.buffy` and for `fq_2lrr.buffy` under the same arrivals; the gap
     measures how much the modelling choice matters.
   - Make the activation order of finding 3 an MDP choice: `Pmax − Pmin` is its effect.
4. **Token bucket (FPerf: some step dequeues more than the rate).** Under arrivals of mean rate r
   (Bernoulli batches or Poisson-like), compute:
   - `P[a step dequeues > RATE]`, the burst a TBF lets through, against r and the bucket size;
   - `E{excess}=? [C<=T]` with a reward on dequeues above the rate.

   This gives the bucket size that keeps bursts rare, which FPerf's yes/no answer cannot.
5. **Loom (FPerf: tenant 2 gets more than 3 packets more than tenant 1 over the last 4 steps, with
   memcached idle and both tenants busy).**
   - `P[isolation violated]` as a function of the tenants' offered loads and of memcached's share;
     memcached is high priority at the NIC, so a small share may already break isolation.
   - FlowEnq's drop freedom (finding 3) as an adversary: `Pmax`/`Pmin` show whether that unintended
     behaviour changes the answer.
6. **Leaf-spine (FPerf: a flow from server 0 to server 5 gets at most 4 packets in 10 steps, every
   queue sending to one fixed destination).**
   - The ECMP spine choice (`meta2`) is a hash: model it as a uniform random choice per packet (or
     per flow) instead of FPerf's adversary. Then `P[throughput ≤ 4]` is the probability that
     collisions on a spine starve the flow.
   - `P[collision | k flows]` gives the number of competing flows at which that becomes likely.
   - The crossbar's free choice of stable matching (finding 3) as an MDP choice brackets the effect
     of the matching policy, and Gale–Shapley gives one point inside the bracket.
   - This is the clearest case of "more informative": FPerf can only say that some hash assignment
     starves the flow, while the probability says how often a random hash does.

**Scale.** The leaf-spine fabric has 643 state variables and Loom 301 (at capacity 10). Both are
SMC-only, so they go to `modes` or the native simulator, with `--stop-at-horizon` and importance
splitting on the derived importance functions for the rare events (Loom isolation, ECMP
starvation). The other four are small enough for exact checking at reduced capacities.
