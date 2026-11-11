# Case study D: tenant isolation on a multi-queue NIC (Loom / MQPrio)

*Draft, in the style of `draft/case-studies-intro.md`.*

**The contention point.** A server's NIC transmits for two tenants over one link. Tenant 1 runs a
Spark job. Tenant 2 runs Spark and memcached. The intended policy is the one Loom (NSDI'19) argues
for:
1. the tenants share the link fairly;
2. within tenant 2, latency-sensitive memcached goes before its own Spark traffic.

Linux's MQPrio cannot express this hierarchy. It maps traffic classes to NIC queues, so the closest
configuration puts every memcached packet in a high-priority NIC queue and all Spark packets, of
either tenant, in a low-priority one. FPerf models exactly this pipeline (`LoomMQPrio`). Each core
has one queue per flow, a per-core stage that interleaves tenant 2's two flows, and a per-core round
robin between the tenants. Then the NIC sorts the cores' packets into the two priority queues, strict
priority sends one packet per step, and a demultiplexer returns it to its tenant.

```mermaid
flowchart LR
    subgraph C["each core (NC cores)"]
      direction TB
      f1["tenant 1 Spark"] --> t1["tenant-1 queue"]
      f2["tenant 2 Spark"] --> t2["tenant-2 queue<br/>(Spark and memcached interleaved)"]
      fm["tenant 2 memcached"] --> t2
      t1 --> rr{{"round robin<br/>1 packet / step"}}
      t2 --> rr
    end
    rr --> NIC{"NIC: MQPrio"}
    NIC --> hi["high: memcached (any core)"]
    NIC --> lo["low: Spark (both tenants, FIFO)"]
    hi --> out(("link<br/>1 packet / step"))
    lo --> out
    out --> T1["tenant 1"]
    out --> T2["tenant 2"]
    style lo fill:#fff3cd,stroke:#b90
    style T1 fill:#f8d7da,stroke:#c33
```

**The bad event `Q`.** Tenant 1 is *starved* in a window of W = 20 steps (after 40 steps of warm-up)
when two things hold:
- it had packets waiting at every step of the window;
- it still received at most 40% of the window's packets, where its fair share is 50%.

The first condition matters. FPerf's own query ("tenant 2 receives more than 3 packets more than
tenant 1") also holds when tenant 1 simply has nothing to send. That is not an isolation failure.

**The input parameters.** Offered loads as fractions of the link: ρ₁ (tenant 1 Spark), ρ₂ (tenant 2
Spark), ρ_m (memcached). Each core's flow of a kind sends a packet per step with probability ρ/NC.

**The model.** `buffy/examples/jani/loom_isolation.buffy` is a DTMC whose only randomness is in the
arrivals. `POLICY` selects the NIC:
- 0: MQPrio, as above;
- 1: the hierarchical policy. There is one NIC queue per tenant, with tenant 2's memcached ahead of
  its own Spark, and a round robin between the tenants.

Everything before the NIC is the same under both policies. The model has 317 state variables at 4
cores with queue capacity 10, too large for exact checking. Numbers come from the native JANI
simulator (`src/netmdp/sim`), with 20,000 runs per point and 95% CI half-width at most 0.007.

**Validation.**
- With its defaults and `POLICY = 0`, the compiled model is proven equivalent to FPerf's hand-written
  `LoomMQPrio` network: for every workload, up to T = 2 and 3 steps, the two dequeue and deliver
  the same packets (`buffy/test/fperf/fperf_equiv_test loom-isolation`, with FPerf's dropping of
  unforwarded packets disabled).
- An independent Python Monte Carlo written from FPerf's module code (`experiments/buffy_fperf/
  loom_oracle.py`) agrees at ρ = (0.6, 0.6, 0.1). MQPrio gives 0.374 ± 0.007 against 0.371 ± 0.007,
  with identical expected shares. The hierarchical policy gives 0 for both.

**Result 1: MQPrio is unfair in short windows even without memcached.** At ρ₁ = ρ₂ = 0.6 and no
memcached, both tenants get on average half of the link (9.94 and 9.96 of 20 packets). Yet tenant 1
is starved in **18%** of windows. With the hierarchical policy it never is (0 in 20,000 runs).

The cause is the NIC's single Spark queue. It takes the cores' packets in core order and in arrival
order, blind to tenants, so over 20 steps tenant 1's share follows a random walk. The hierarchical
policy alternates between tenants whenever both have packets waiting, and gives exactly half.

**Result 2: a small memcached share makes it likely.** Tenant 1 is starved with these probabilities
(ρ₁ = ρ₂ = 0.6; 20,000 runs per point, 95% half-width ≤ 0.007):

| ρ_m | 0 | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
|---|---|---|---|---|---|---|
| MQPrio | 0.181 | 0.273 | 0.371 | 0.478 | 0.579 | 0.758 |
| tenant 1's expected share (of 20) | 9.94 | 9.47 | 8.99 | 8.49 | 7.99 | 6.98 |
| hierarchical | 0 | 0 | 0 | 0 | 0 | 0 |

The mean moves exactly as strict priority predicts: memcached comes out of the Spark that both tenants
share, so tenant 1 loses ρ_m/2 of the link. The probability of a visibly unfair window rises much
faster than the mean. Memcached at 10% of the link costs tenant 1 only 5% of its share on average,
but doubles the chance that it is starved (0.18 to 0.37).

**Monotonicity.** On every pair of grid points that differ in one load (ρ₁, ρ₂ ∈ {0.5, 0.6, 0.7},
ρ_m ∈ {0, 0.05, …, 0.3}), the probability of starvation:
- rises with ρ_m: at (0.5, 0.7), 0.494, 0.598, 0.685 for ρ_m = 0.05, 0.1, 0.15; at (0.7, 0.5),
  0.095, 0.163, 0.247;
- rises with tenant 2's load ρ₂: 0.254 to 0.598 at ρ₁ = 0.5; 0.163 to 0.402 at ρ₁ = 0.7;
- falls with tenant 1's load ρ₁: 0.598 to 0.402 at ρ₂ = 0.7; 0.254 to 0.163 at ρ₂ = 0.5.

So a box is certified by its corner with the least memcached, the least tenant-2 Spark and the most
tenant-1 Spark.

**The assumption found: a mild box.**

> A = (0.5 ≤ ρ₁ ≤ 0.6) ∧ (0.6 ≤ ρ₂ ≤ 0.7) ∧ (0.1 ≤ ρ_m ≤ 0.2)

Both tenants offer at least half the link. Tenant 2's Spark is at least as heavy as tenant 1's, and
memcached is a modest 10–20% of the link. By monotonicity, the box's least favourable corner is
(0.6, 0.6, 0.1):

| point of A | MQPrio | hierarchical |
|---|---|---|
| least favourable corner (0.6, 0.6, 0.1) | **0.371** | 0 |
| centre (0.55, 0.65, 0.15) | 0.592 | 0 |
| most favourable corner (0.5, 0.7, 0.2) | 0.765 | 0 |

Across the whole box, P[starved] ≥ 0.37 under MQPrio, and 0 under the policy MQPrio was meant to
implement. Nothing in A is extreme: no tenant floods the link, and memcached is a minority of the
traffic.

**Obvious regions, for contrast.**
- **Memcached takes half the link** (ρ_m = 0.5). Starvation is near-certain (0.943) and tenant 1
  gets a quarter of the link; anyone would predict this from strict priority.
- **Tenant 1 barely sends.** It is never starved by this definition, because it is not waiting.
  FPerf's original query would still flag it.

The finding lies between: at a memcached share an operator would think harmless, an isolation
failure that tenant 1 would notice happens in more than a third of the windows. A third of the risk
at the corner (0.18 of 0.37) is there even without memcached.

**Scale.** At 8 cores the corner's probability is unchanged: 0.365 ± 0.009 from the compiled model
(10,000 runs), 0.367 ± 0.007 from the oracle. The hierarchical policy stays at 0. The effect depends
on the shares of the link, not on the number of cores. The FPerf-sized NIC (queue capacity 10) is
kept, because at capacity 32 and 8 cores the step has about 970,000 DAG nodes, beyond what the native
compiler handles in reasonable time.

**Cross-checks with the oracle** (20,000 runs each; all within the confidence intervals):

| point | model | oracle |
|---|---|---|
| (0.6, 0.6, 0.1), 4 cores | 0.371 ± 0.007 | 0.374 ± 0.007 |
| (0.6, 0.6, 0.1), 8 cores | 0.365 ± 0.009 | 0.367 ± 0.007 |
| (0.5, 0.7, 0.15) | 0.685 ± 0.006 | 0.688 ± 0.006 |
| (0.55, 0.65, 0.15) | 0.592 ± 0.007 | 0.597 ± 0.007 |
| hierarchical, all checked points | 0 | 0 |

**Reproduce.**
- `experiments/buffy_fperf/run_loom_iso.sh` and `run_loom_box.sh` produce `results/loom_iso_sweep.log`
  and `loom_box.log` with the native simulator, using `loom_eval.py` (one pass per point).
- `loom_oracle.py` is the oracle.
- `buffy/build/fperf_equiv_test loom-isolation` is the FPerf equivalence.

**Why this supports the paper.** It applies the recipe to a NIC rather than a switch or a GPU, and
the contention point is a *policy* mismatch: a hierarchical intent forced into a flat priority
scheme. Two features make the probabilistic answer the informative one:
- **The variance effect.** The expected shares are equal when there is no memcached, so a mean-value
  or long-run analysis would call MQPrio fair. A FORALL query would call it unfair, but only by
  exhibiting an adversarial arrival order. The probability says how often a tenant actually sees an
  unfair window.
- **Scale.** The answer moves gradually with a mild memcached share, not with an extreme one.
