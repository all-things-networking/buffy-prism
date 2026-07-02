# Notes — queue-based chunked scheduler (v2, `scheduler_queue.pm`)

The realistic redesign from the design review: **no scheduler privilege for the
victim** (Q3), **decoupled prompt/output length** (Q6), and a **real waiting queue with
evict-to-queue** (Q8). Unified request records (`empty|waiting|running`); the victim is
an ordinary record that competes for `N_SLOTS` batch slots and is admitted/evicted by
the same FCFS/LIFO rules as background. See header of `scheduler_queue.pm`.

Still exact-checkable at the exploration scale (~182k states); intended for SMC at
realistic scale (see `../PARAMETERS.md`).

## What the redesign revealed (important)

**v1's "victim gets preempted" finding was partly an artifact** of the privileged
setup (dedicated slot + 3 concurrent requests). With a realistic slot limit
(`N_SLOTS=2`) and the victim competing, the small victim co-runs with at most one
background request, so `victim_blk (≤2 while decoding) + bg_blk (≤6) ≤ KV_CAP=8` — the
victim can **never** push the pool over the cap, so **P(victim preempted) = 0**. The
victim's real harm is **queueing delay**: waiting for a slot behind long requests. (This
is exactly the FQ-CoDel-standard critique paying off.)

## The robust finding — queueing delay, timing not volume

`POLICY=fcfs, p_arr=0.5, p_lp=0.4, p_ol=0.4`. Bad event = victim TBT stall
(`v_maxgap ≥ SLO_TBT`), baseline **0.108**:

| condition C on the request pattern | P(stall \| C) | P(C) | vs baseline |
|---|---|---|---|
| a long-prompt bg arrived **before** the victim, none after | **0.221** | 0.19 | **2.0×** |
| the same longs arrived **after** the victim, none before | **0.018** | 0.34 | 0.17× (protective) |
| ≥2 long requests arrived (volume) | 0.163 | 0.50 | 1.5× |
| long in **both** prompt & output (`n_lp≥2 & n_lo≥2`) | **0.236** | 0.24 | **2.2×** |

- **Timing, not volume:** a long request arriving *before* the victim holds a slot long
  enough that the victim queues behind it and its first/next token is delayed. The same
  longs arriving *after* the victim are *protective* (it already holds/obtains a slot).
- **Decoupling pays off (Q6):** requests long in *both* prompt and output hold a slot the
  longest and hurt most — a correlation effect v1 (bundled lengths) could not express.
- Same "mild but informative, invisible per component" character as FQ-CoDel/incast, now
  via a queueing mechanism rather than eviction.

## Caveats / next steps

- At this tiny scale, `preempts` never reaches 2 (only 2 slots → no in-iteration cascade)
  and victim preemption is 0; preemption bad events need the larger validation config
  (more slots, bigger KV) — where they should re-emerge. Run under SMC (`../PARAMETERS.md`).
- Victim arrival `T_V=3` is still fixed (a legitimate input assumption, not a privilege);
  sweep it to confirm robustness.
- TODO: a `scheduler_queue.props` + runner mirroring `scheduler.props`/`run_case_study.sh`
  for one-command reproduction; a tunable prompt↔output correlation (condition `p_ol` on
  prompt class); the larger SMC validation config + a slot generator (PRISM has no arrays).
- `scheduler.pm` (v1, exact, privileged victim) is kept as the initial-exploration
  artifact; `scheduler_queue.pm` (v2) is the more faithful model going forward.
