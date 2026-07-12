# Incast case study — handoff notes

Notes for picking this up and continuing on your own. It's the same *style* as
your FQ-CoDel example (DTMC + `P=?` path properties, checked in PRISM simulation
mode), applied to a top-of-rack (ToR) switch during TCP incast. If you know the
FQ-CoDel model, the "common abstraction" section at the end maps the two.

## Contents
1. [TL;DR](#1-tldr)
2. [Repo layout](#2-repo-layout)
3. [The contention model](#3-the-contention-model)
4. [Modeling choices (and why)](#4-modeling-choices-and-why)
5. [The property we check](#5-the-property-we-check)
6. [The method: an assumption is a *box*, certified by a corner](#6-the-method-an-assumption-is-a-box-certified-by-a-corner)
7. [What was tried and what was found](#7-what-was-tried-and-what-was-found)
8. [How to run it](#8-how-to-run-it)
9. [Validation status](#9-validation-status)
10. [Caveats / things to double-check](#10-caveats--things-to-double-check)
11. [Suggested next steps](#11-suggested-next-steps)
12. [Relation to the FQ-CoDel model](#12-relation-to-the-fq-codel-model)

---

## 1. TL;DR
- **Contention point:** a ToR switch. Many uplink ports, each with a shallow
  buffer, all forwarding into **one output port** (the receiver-facing link)
  that drains **1 packet/slot**. Classic incast.
- **Bad event `Q`:** at least `THRESH` packets dropped at the output buffer
  (receiver-facing loss). Tracked as `odrops`.
- **Assumption `A`:** a **range (box)** over the *input-traffic* parameters —
  total senders `M`, sync window `WIN`, burst/flow length `SLEN`. `BUF` (switch)
  and `THRESH` (severity) are held fixed.
- **The question the tool answers:** `P[Q | A]` — and we look for a *mild /
  non-obvious* box where `Q` is likely for **every** point in it.
- **Two examples found** (each self-contained under `model/`):
  - **example 1 (moderate fan-out):** `A = (6≤M≤12) ∧ (0≤WIN≤48) ∧ (16≤SLEN≤24)`,
    `BUF=32, THRESH=8` → `P[Q] ≥ 0.64` everywhere.
  - **example 2 (incast without synchronisation):** `A = (16≤M≤20) ∧
    (48≤WIN≤96) ∧ (8≤SLEN≤12)` → `P[Q] ≥ 0.54` everywhere, with the
    least-favorable corner at `WIN/SLEN = 12` (senders spread over twelve
    flow-lengths — genuinely de-synchronised) and every input buffer healthy.
- **Checked in PRISM simulation mode** (exact is intractable), cross-checked
  against a NumPy oracle (`incast_sim.py`) that implements identical dynamics.

## 2. Repo layout
```
README.md                       one-paragraph overview + quick start
HANDOFF.md                      this file
tools/gen_incast.py             generates incast.pm for any MMAX (even)
model/
  example1_moderate_fanout/     hand-written, richly commented reference model
    incast.pm  incast.props  incast_sim.py  NOTES.md
  example2_desync_short_bursts/ auto-generated model (MMAX=20, 10 uplinks)
    incast.pm  incast.props  incast_sim.py  NOTES.md
```
Each example folder is standalone: `.pm` model, `.props` queries, `incast_sim.py`
oracle (its `__main__` certifies that example's box), and a `NOTES.md` writeup
with numbers and discussion. **Read `example1/incast.pm` first** — it's the
annotated one; example 2 is the same dynamics at larger scale.

## 3. The contention model
Discrete time; one **slot** = one packet transmission time on the
receiver-facing link.

```
   uplink 1 (2 flows) ->[ q1 ]--.
   uplink 2 (2 flows) ->[ q2 ]--+\                     .--------.
        ...                      +--> (switch fabric) ->|  qo    |--> receiver
   uplink U (2 flows) ->[ qU ]--'/                      '--------'
```
- **`MPP = 2` flows per uplink** (fixed). The single input-traffic knob is
  **`M` = total senders**, so the number of active uplinks is `M/2`. Senders
  `1..M` are "on"; the rest are idle (their port is outside the fan-out).
- Every buffer (each `qj` and `qo`) has the **same capacity `BUF`**.
- Each sender picks a start slot uniformly in `[0..WIN]` and sends `SLEN`
  packets back-to-back, one per slot.

**Per-slot service (deterministic), order matters:**
1. output drains 1 to the receiver: `qo = max(qo-1, 0)`;
2. every **backlogged** input port forwards 1 into `qo` (so up to `#backlogged`
   packets arrive at `qo` this slot); the output admits up to its remaining
   room and **drops the overflow** → these are the **output drops** (`Q`);
3. new arrivals enter the input buffers; overflow there = **input drops**.

The key structural fact that drives everything: each input port forwards **≤ 1
packet/slot**, and the output drains **≤ 1/slot**, so the output can only
overflow when **≥ 2 input ports are backlogged simultaneously** for long enough.
That's why *fan-out / fan-in* — not per-port load — governs receiver loss.

**One slot concretely** (example: 3 ports backlogged, `qo=BUF-1`): output drains
1 → room 2; 3 ports forward → 2 admitted, **1 dropped at output**; then arrivals
land in the input buffers. `odrops += 1`, `slot++`.

## 4. Modeling choices (and why)
- **Two clocks: `slot` and `stage`.** Within a slot, each of the `MMAX` senders
  flips an independent "start now?" coin; a single DTMC command can't enumerate
  `2^MMAX` joint outcomes, so we sequence them: `stage` walks `1..MMAX` (one
  sender each), then `stage = MMAX+1` does the deterministic service, then back
  to 1 and `slot++`. So one real slot = `MMAX+1` micro-steps. (Same trick as
  FQ-CoDel's per-queue stages.)
- **Uniform start via a hazard, no `WIN`-many branches.** A still-waiting sender
  starts this slot with prob `hz = 1/(WIN+1-slot)`. Conditioned on not having
  started, that is exactly uniform on `[0..WIN]` (and `hz=1` at `slot=WIN`, so
  everyone has started by then). Keeps the model compact and `WIN`-agnostic.
- **`active` from `(on, t)`.** A sender records its start slot `t`; it is active
  (sending) while `on=1 & slot - t < SLEN`. No per-sender countdown needed.
- **Run to full drain.** `HORIZON = WIN + M*SLEN + SLEN`. Drops can happen well
  *after* the last arrival, while backlogged uplinks keep draining into the
  output — see the artifact in §7. Do **not** shorten this.
- **Drop counters capped at `THRESH`** (`odrops, idrops : [0..THRESH]`): once
  `Q` holds it stays, and it keeps the variables finite.
- **All buffers = one `BUF`** (your constraint). `BUF` and `THRESH` are fixed
  switch/severity constants, *not* input-traffic parameters, so the assumption
  box ranges only over `M, WIN, SLEN`.

## 5. The property we check
`incast.props`:
```
P=? [ F ("done" & odrops>=THRESH) ]     // (1) P[Q] : receiver-facing incast loss
P=? [ F ("done" & idrops>=THRESH) ]     // (2) input-buffer loss (contrast)
P>=0.5 [ F ("done" & odrops>=THRESH) ]  // (3) true/false: is Q likely here?
```
`"done"` is `slot = HORIZON` (an absorbing state where `odrops/idrops` hold their
final totals). So `P[F(done & X)]` = probability `X` holds at end of run.

## 6. The method: an assumption is a *box*, certified by a corner
The assumption `A` is a **box**: a range on each input-traffic parameter, e.g.
`A ≡ (M∈[6,12]) ∧ (WIN∈[0,48]) ∧ (SLEN∈[16,24])`. It applies to **every**
combination inside. We want boxes where `P[Q]` is non-negligible **throughout**,
not boxes whose average is carried by one extreme corner.

Empirically (checked at many points, never violated) `P[Q]` is **monotone**:
increasing in `M` and `SLEN`, decreasing in `WIN`. Therefore the box **minimum**
sits at the corner `(M_lo, WIN_hi, SLEN_lo)` and the **maximum** at
`(M_hi, WIN_lo, SLEN_hi)`. So you can **certify a whole box by checking two
corners** — in particular, if `P[Q]` at the least-favorable corner is high, it's
high for all of `A`.

**The pitfall this rules out.** A box like `(2≤M≤12) ∧ (0≤WIN≤64) ∧ SLEN=24`
looks dangerous on average, but its least-favorable corner `(M=2, WIN=64)` has
`P[Q]=0` (a single uplink can never overflow the 1/slot output). Its "danger" is
entirely the synchronised / high-fan-in corner. Corner-certification exposes
this immediately, which is why the real boxes start at `M=6` / `M=16`.

## 7. What was tried and what was found
Roughly chronological, so you can see the dead ends too.

**(a) First model — single shared buffer (superseded, not in repo now).** `N`
senders, one buffer, bad event = buffer overflow. Conditions were *within-run*
input features (peak concurrency, spread of starts, #early starters). It worked
but didn't model the ToR topology; replaced by the two-tier switch model.

**(b) ToR model with servers + uplinks.** 2 server ports + uplink ports;
`FANOUT` = number of active uplinks was the swept knob. Finding: receiver loss is
driven by fan-out, and **every input buffer stays healthy** (`P[input loss]=0`)
while the receiver overflows — the contention is invisible per-port. This became
the direction. (Later simplified per request to *all uplinks*, one knob `M`.)

**(c) A simulation artifact worth knowing about.** An early oracle stopped the
run at `WIN+SLEN` instead of running to full drain. That produced a dramatic but
**false** "a moderate sync window is worse than tight sync" reversal — it was
dropping the post-arrival drain phase, during which backlogged uplinks keep
feeding the output. **Cross-checking the PRISM model against the oracle caught
it**; with draining included, both agree and the reversal disappears (tight sync
is simply worst — the obvious direction). Lesson: always run to full drain, and
keep the PRISM↔oracle cross-check.

**(d) `SLEN` sanity from the literature.** Incast-causing flows are *short*:
partition-aggregate responses ~1.6–2 KB ≈ 1–2 packets (DCTCP, SIGCOMM'10);
general query traffic 2–20 KB; storage/Hadoop SRUs "small chunks 1–256 KB",
typically tens of KB ≈ up to ~20 packets (Phanishayee, FAST'08). Fan-in is large
(tens of responders). So `SLEN` in the low tens of packets is realistic; example
1's `SLEN∈[16,24]` is at the large/storage end.

**(e) The two boxes found** (both `BUF=32, THRESH=8`):

*Example 1 — moderate fan-out.*
```
A = (6 ≤ M ≤ 12) ∧ (0 ≤ WIN ≤ 48) ∧ (16 ≤ SLEN ≤ 24)
least-favorable corner (M=6, WIN=48, SLEN=16): P[Q] = 0.64   -> holds for ALL of A
most-severe     corner (M=12, WIN=0, SLEN=24): P[Q] = 1.00
P[input loss] = 0 everywhere.
```
Surface at `SLEN=24` (M=2 = one uplink, outside A):
```
          WIN=0  8    16   32   48   64
M=2       0.00 0.00 0.00 0.00 0.00 0.00
M=4       1.00 1.00 0.90 0.60 0.33 0.17
M=6       1.00 1.00 1.00 1.00 1.00 1.00
M=8       1.00 1.00 1.00 1.00 1.00 1.00
```

*Example 2 — incast without synchronisation (the less-obvious one).*
```
A = (16 ≤ M ≤ 20) ∧ (48 ≤ WIN ≤ 96) ∧ (8 ≤ SLEN ≤ 12)
least-favorable corner (M=16, WIN=96, SLEN=8): P[Q] = 0.54   WIN/SLEN = 12x
most-severe     corner (M=20, WIN=48, SLEN=12): P[Q] = 1.00
P[input loss] = 0 everywhere.  (Trim WIN<=80, still 10x, and the whole box is >=0.98.)
```
The point of example 2: the senders are genuinely de-synchronised (started over
a window 8–12× a flow length, so pairwise collisions are rare and only a small
fraction transmit at any instant), yet a realistic fan-in of short flows still
overflows the receiver. Incast is about *aggregate coincidence*, not
synchronisation.

## 8. How to run it
PRISM 4.8.1 was used. `M` is even (= 2 × active uplinks). Exact model checking
OOMs at this scale, so use **simulation (SMC)**, same as your FQ-CoDel runs.

```
cd model/example1_moderate_fanout      # or example2_desync_short_bursts

# whole box (an experiment over the ranges):
prism incast.pm incast.props -prop 1 \
  -const BUF=32,THRESH=8,M=6:2:12,WIN=0:8:48,SLEN=16:4:24 \
  -sim -simmethod ci -simwidth 1e-3 -simconf 0.01 -simpathlen 5200

# single least-favorable corner (certifies the whole box):
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=6,WIN=48,SLEN=16 \
  -sim -simmethod ci -simwidth 1e-4 -simconf 0.01 -simpathlen 5200

# oracle, no PRISM needed (prints the box certification for that example):
python3 incast_sim.py
```
- **Path length matters:** a run is `(MMAX+1)*HORIZON` micro-steps. Example 1
  (`MMAX=12`) needs ~5200; example 2 (`MMAX=20`) needs ~8000. Too small and the
  run never reaches `"done"`.
- **Regenerate a model at another fan-in:** `python3 tools/gen_incast.py 24 >
  incast.pm` (argument = `MMAX`, even; ports = `MMAX/2`). Example 2 was made this
  way. Example 1's file is hand-annotated but structurally the same.

## 9. Validation status
PRISM simulation and the oracle agree at every checked point. Spot checks
(`BUF=32, THRESH=8`):

| point | PRISM | oracle |
|---|---|---|
| ex1 `M=6, WIN=48, SLEN=16` (least-fav corner) | 0.639 | 0.644 |
| ex1 `M=8, WIN=24, SLEN=24` | 1.00 | 1.00 |
| ex1 `M=2, WIN=0, SLEN=24` | 0.00 | 0.00 |
| ex2 `M=16, WIN=96, SLEN=8` (least-fav corner) | 0.538 | 0.539 |
| ex2 `M=20, WIN=48, SLEN=12` | 1.00 | 1.00 |

## 10. Caveats / things to double-check
- **PRISM reserved single letters.** `S, W, B, C, G, P, R, F, U, X` are
  operators; that's why the consts are `SLEN, WIN, BUF, THRESH, M, MPP` etc. If
  you add constants, avoid single letters.
- **`WIN=0` range bug.** The start-slot variable range is `[0..TWIN]` with
  `TWIN = max(WIN,1)`, because PRISM rejects a degenerate `[0..0]` range. Keep
  that if you touch the declarations.
- **Monotonicity is empirical, not proved.** Corner-certification relies on it.
  It held in every check, but if you change the dynamics, re-verify a few
  interior points before trusting a two-corner certificate.
- **`BUF` and `THRESH` are fixed, not swept.** They're not "input traffic," so
  the assumption box is only over `M, WIN, SLEN`. If you'd rather present them as
  part of `A`, that's a modeling decision to make explicitly.
- **Model is output-queued with full fabric speedup** (every backlogged input
  port can deliver to `qo` each slot). Real switches have limited speedup and
  often a *shared* buffer with dynamic thresholds rather than equal per-port
  `BUF`. Both are reasonable next refinements (see below).
- **Example-2 corner is `0.54`** (just above half) at the aggressive `12×`
  desync; `≥0.98` if you trim `WIN` to `10×`. Two open calls for ATN: which tone
  to headline, and whether the larger `MMAX=20` model is fine or should shrink.

## 11. Suggested next steps
- **Tighten CI** on the headline corners to your usual `simwidth=1e-4` for the
  paper numbers (the tables above used looser widths for speed).
- **Sweep `BUF` and `THRESH`** to show the box moves predictably (bigger buffer
  → need more fan-in; this is a good robustness/representativeness figure).
- **Shared-buffer variant:** replace equal per-port `BUF` with a shared pool +
  dynamic threshold (closer to real ToR silicon). Would change where the
  fan-out threshold lands.
- **MDP variant** (like your FQ-CoDel MDP): make arrivals/starts nondeterministic
  instead of uniform, and report `Pmax/Pmin` — gives a worst-case bracket on
  `P[Q|A]` without committing to the uniform-start distribution.
- **Reward metric** for *expected* drops (not just `P[≥THRESH]`), to complement
  the threshold event.
- **Automate box search:** a small script over `incast_sim.py` that, given a
  target `P[Q]` floor, finds the mildest box (largest `WIN/SLEN`, smallest `M`)
  whose least-favorable corner clears it. Right now this was done by hand.

## 12. Relation to the FQ-CoDel model
Same abstraction, which is the point for the paper:

| | FQ-CoDel example | this incast example |
|---|---|---|
| type | DTMC, PRISM SMC | DTMC, PRISM SMC |
| probabilistic input | per-slot uniform arrivals | per-sender uniform start (hazard) |
| deterministic core | the AQM scheduler + queues | switch fabric + buffers |
| bad-event counter | `iq5_deqs_bl` | `odrops` (and `idrops`) |
| condition/assumption | predicate over input-describing state (`time`, `iq5_cenq`, `iq5_aipg`) | **range/box** over input-traffic params (`M`, `WIN`, `SLEN`) |
| analysis primitive | `P[¬Q ∧ A] / P[A]` | `P[Q ∧ A] / P[A]` ≈ `P[Q]` over the swept box |

The main new idea here vs FQ-CoDel is that the **assumption is a range**, and we
certify it holds across the *whole* range (via monotonicity + corner checks)
rather than reporting a single point.
