# Buffy programs for the incast and LLM batch-scheduler case studies

These runs compare two Buffy programs with the hand-written PRISM models of the other two case
studies:

- `buffy/examples/jani/incast.buffy` is checked against `hand/incast.pm`. The hand model is
  `model/example2_desync_short_bursts/incast.pm` on branch `incast-buffer-case-study` (0271891),
  generated for 20 senders.
- `buffy/examples/jani/llm_sched.buffy` is checked against `hand/llm_scheduler.pm` and
  `hand/llm_scheduler_big.pm`. These are `model/llm_batch_scheduler/chunked/scheduler.pm` (3
  records) and `scheduler_big.pm` (8 records, from `gen_scheduler.py`), both on branch
  `llm-batch-scheduler-case-study` (f4ff984).

The hand models are copied here unchanged. The `buffy` submodule must include the two programs
(Buffy branch `case-studies`, which also adds `--stop-at-horizon`).

| script | does |
|---|---|
| `cmp_exact.sh incast "M WIN SLEN BUF THRESH" ...` | exact check on small configurations: the hand model and the compiled PRISM, both with the PRISM explicit engine |
| `cmp_exact.sh llm "T_V N_SLOTS KV_CAP CHUNK_BLK POLICY ADM_POLICY p_arr p_lp p_ol_sp p_ol_lp" ...` | exact check: the hand model with the PRISM explicit engine, the compiled JANI with `mcsta` |
| `run_smc.sh` | full size, 20,000 runs each: `modes` on the compiled JANI, `prism -sim` on the hand models |

Raw output is in `results/`. Exact checking is used only on the small configurations, and every
run is capped by `timeout`.

## How the programs model the case studies

**Incast.** The program has one method, `tor`. In each time step:

1. the output port drains one packet;
2. every backlogged uplink forwards one packet into the output buffer, where packets are
   tail-dropped when it is full;
3. every responder whose delay has run out appends one packet to its uplink.

This is the hand model's order: a packet sent in slot t is forwarded in slot t+1 at the earliest.
Each response is preloaded into a socket buffer at time 0. The start delay is drawn once, at
time 0, as the arrival count of a capacity-0 buffer, and is kept in a global that counts down.
The hand model draws the same uniform start times with the per-slot hazard 1/(WIN+1−slot). The
number of senders is the array size `M`, so there is no `MMAX` padding. The monitors `odrops` and
`idrops` count output and uplink losses, computed from the room in the buffer before each move.

**LLM scheduler.** Requests are records held in method globals (`st`, `pp`, `oo`, `bk`, `ad`;
arrays over `R` records, with record 0 tracked). The iteration runs these steps in order:

1. inject the tracked request;
2. draw at most one background arrival (one five-valued count of a capacity-0 buffer: none or
   one of the four shapes);
3. admit up to `R` waiting records (smallest key first);
4. serve every record in order;
5. evict up to `R` times, latest arrival first.

The instrumentation of the hand model is `//@` monitors. The program follows `gen_scheduler.py`,
so the same file gives the 3-record and the 8-record model (`-D R=8 ...`). Queries are the
`scheduler.props` triples, read at the horizon: `F<=T (time == T & ...)`.

## Results

### Exact, small configurations

Every property agrees with the hand model to 1e-15, in every configuration tried.

| incast (M WIN SLEN BUF THRESH) | loss | iloss | hand states (boundary) | Buffy PRISM states (boundary) |
|---|---|---|---|---|
| 4 4 3 3 2 | 0.8336 | 0.04 | 216,272 (10,354) | 31,097 (3,369) |
| 4 6 4 3 2 | 0.925031 | 0.325281 | 1,102,427 (52,696) | 156,273 (17,053) |
| 6 3 3 4 2 | 1.0 | 0.0 | 1,895,261 (90,906) | 216,353 (16,223) |

Two larger configurations could not be compared. At (6 5 2 2 2) and (8 3 2 3 2), the hand model
did not finish within the 600 s cap. The compiled model gave exact results: 2,332,215 states with
loss 0.992284, and 3,069,257 states with loss 1.0.

"Boundary" counts the states at the time-step boundaries: `stage=1` in the hand model, `stage=0`
in the compiled PRISM. The compiled JANI (sync layout) has exactly the boundary states.

| LLM (T_V N K CB POL ADM p_arr p_lp p_ol_sp p_ol_lp) | stall | a_joint | preempted | cascade | hand states (boundary) | Buffy JANI states |
|---|---|---|---|---|---|---|
| 3 2 8 3 0 0 .7 .4 .4 .4 | 0.056448 | 0.012990 | 0 | 2.886e-4 | 307,766 (39,234) | 91,131 |
| 2 3 6 3 1 0 .8 .5 .3 .6 | 0 | 0 | 0 | 0.521907 | 392,533 (50,759) | 141,573 |
| 3 2 6 1 0 1 .6 .4 .5 .5 | 0.2118 | 0.078669 | 0.110208 | 0.008467 | 200,766 (27,145) | 237,841 |
| 2 3 5 2 0 0 .9 .3 .2 .7 | 0.287826 | 0.083139 | 0.415110 | 0.551565 | 385,975 (51,836) | 279,048 |
| 4 1 8 3 1 1 .5 .6 .4 .4 | 0.225 | 0.072363 | 0 | 0 | 183,277 (26,139) | 168,551 |

Every other conditional triple (groups a to f) also agrees. These configurations cover both
eviction policies, both admission policies, chunk sizes 1 to 3, correlated output lengths, and
configurations with and without evictions of the tracked request.

### Full size, statistical (20,000 runs)

| model | Buffy JANI, `modes` | hand PRISM, `prism -sim` | earlier reported |
|---|---|---|---|
| incast, M=16 WIN=96 SLEN=8 BUF=32 THRESH=8: loss | 0.538, 95% CI [0.531, 0.545], 130 s | 0.539 ± 0.009 (99%), 311 s | 0.538 (PRISM), 0.536 (oracle) |
| incast, same: iloss | 0 (95% upper bound 1.8e-4) | – | 0 |
| LLM, 8 records, T=40, p_lp = p_ol = 0.5: stall | 0.475, 95% CI [0.468, 0.481], 324 s (all 15 properties) | 0.477 ± 0.009 (99%), 61 s | 0.481 (`VALIDATION.md`) |

## What this says about the compiler design

1. **Both case studies fit the current language and compile exactly.** No compiler change was
   needed for the semantics. The one bug found was in the PRISM backend: PRISM rejects one-value
   ranges like `[0..0]`, which a capacity-0 buffer produces. It is fixed by emitting one value
   wider.

2. **The sync layout gives fewer states than hand-written sub-stages.** The hand incast model
   resolves each sender in its own sub-stage (21 per slot). That gives it 7 to 9 times the
   states of the compiled PRISM, and 3 to 6 times its boundary states. Part of the boundary gap
   is the hand model's `on_k`/`t_k` per sender against Buffy's delay counters. The JANI sync
   layout has only the boundary states.

3. **Steps past the horizon cost states; `--stop-at-horizon` now removes them.** `horizon T`
   saturates `time`, but the model kept stepping. In the LLM model, 67,188 of the 91,131 states
   have `time = T` and are reached only after the horizon; the hand model stops at `t = T`. With
   `--stop-at-horizon` every step update and staged arrival transition becomes
   `time < T ? update : current value`. The compiler refuses any query that looks past T
   (unbounded `F`/`G`/`U`, larger bounds or monitor horizons, `E` other than `C<=k` and `I=k`
   with k ≤ T).
   - **LLM model:** 39,234 states, exactly the hand model's boundary count. All 15 values are
     identical (`mcsta`; the JANI test suite checks this).
   - **Small examples:** 11 examples given `horizon 10` keep every value in every JANI layout and
     PRISM mode. States shrink by up to 54% (`deck_rr`: 2,010 → 1,075 in the sync layout, 13,720 → 6,329 staged).
   - **Incast:** unchanged, since the network is empty by its horizon.

4. **Same-step random draws are an idiom, not a construct.** A phase's value is visible only in
   the next step, so both programs read a draw as `arrivals-p` of a capacity-0 buffer (§2.9.2 of
   the user guide). It is exact and costs no state, but it is a trick. A first-class
   `random x ~ D;` would be clearer: a per-step network draw, readable in the same step by
   methods, monitors and traffic conditions, and never state. It would also cover a
   *class-valued* arrival ("at most one request, of one of four shapes"). With one traffic source
   per packet class, the classes are independent, so this cannot be stated directly today.

5. **Sources with memory live in the method.** Incast's responders need a timer and a remaining
   count each. Phases cover small Markov-modulated sources but not this: they are scalar (no
   arrays), they are redrawn from distributions with constant support (no `x' = x − 1`), and
   their probabilities are constants. A hazard 1/(WIN+1−t) needs state-dependent probabilities.
   The programs therefore keep sender state in method globals and draw the start time up front,
   which gives the same distribution (verified above). Two small extensions would let the input
   model stay in the network block:
   - probability expressions over boundary state, such as `bernoulli(1.0 / (WIN + 1 - time))`.
     The backends already receive probabilities as expressions; conditional distributions build
     them.
   - arrays of phases with deterministic updates.

6. **`drops-p` sees only traffic drops.** Incast's bad event is a drop at the output port caused
   by a `move-p`, and `drops-p` does not count those. The program computes the losses from the
   room before each move. As a consequence, expected losses (`E{...}[C<=T]`) cannot be written,
   because rewards cannot read method locals. Counting move and flush drops in `drops-p` would
   make output-port loss a one-line reward.

7. **Requests are records, not packets.** LLM requests change state (remaining prefill and
   output, KV blocks) and go back to the queue modified, so they are global arrays. Buffers and
   packet classes go unused. Buffy works here as an imperative step language with monitors,
   queries and layouts; it is not acting as a buffer language. That is a fair use, but it shows
   where its abstractions stop.

8. **Selection loops make deep DSA chains.** Admission and eviction pick a minimum or maximum
   over the records R times. This gives 162 temporaries and 52 assignment levels at R=3, and 902
   and 292 at R=8. The trees without sharing would have 10¹³ and 10⁶⁷ nodes. The effect on each
   backend:
   - JANI sync with transient levels handles it: `mcsta` builds 91,131 states in 2.2 s, Storm in
     29 s.
   - `--no-levels` is refused.
   - PRISM needs staged temporaries. The five-way draw at the start of the step multiplies every
     later stage, giving 2.37 million states, 26 times the boundary count (PRISM explicit takes
     2 min 44 s; the hand model takes 4 s).

   - Simulation pays too. `modes` takes 324 s for 20,000 runs of the 8-record model; `prism -sim`
     takes 61 s on the hand model.

   Possible remedies: an `argmin`/`argmax` builtin that elaborates to one comparison tree per
   record instead of a chain, or moving the draw after the deterministic prefix of the step.

9. **"At the horizon" queries.** Every case-study property is "X holds at time T", written as
   `F<=T (time == T & X)`. Writing it with `given` builds a monitor for the conjunction of two
   `F`s, although the conjunction of two at-T formulas is just the conjunction of the predicates.
   An `at T φ` form would compile without a monitor, so `given` could be used for these triples.

10. **Probability literals.** Constant products such as `P_ARR * (1 - P_LP) * (1 - P_OL_SP)` are
    evaluated in doubles and emitted as decimals (0.30000000000000004, …). They miss 1 by an ulp,
    and `mcsta` warns on every property. The values are unaffected at 1e-15, but emitting exact
    rationals, or the last entry as 1 − Σ of the others, would remove the warnings.

Notes on the hand models, found while matching them:
- In `scheduler.pm`, the eviction score has no "running with blocks" guard under `POLICY=1`.
- In `gen_scheduler.py`, the model would deadlock under `POLICY=1` if the tracked request alone
  overflowed the KV pool.

Neither case is reachable at the sizes used, and the Buffy program evicts only running records
that hold blocks.
