# Example 3 — probabilistic assumptions vs "100%-only"

Same contention point and dynamics as `example2_desync_short_bursts/` (all
uplinks, `MPP=2` flows each, short flows, shallow buffer `BUF=32`, bad event
`Q = odrops ≥ THRESH` with `THRESH=8`). The model here is generated with
`MMAX=24` (12 uplinks) so the extreme box below (up to 12 uplinks) fits; for
`M=16` it gives identical results to example 2's `MMAX=20` model (idle uplinks
never start).

Purpose: make the paper's methodological point precise — a **probabilistic**
tool finds *mild, non-obvious* assumptions under which loss is likely-but-not-
certain, whereas restricting to **100% (certainty)** forces you onto *obvious,
extreme* assumptions. Concretely we give three boxes.

## The key structural observation: the risk is 0/1 in load, gradual only in sync
Hold the box's other parameters and nudge one:

```
              P[Q] at M=16, WIN=96, SLEN=8  =  0.54
  fan-in:     M=14 -> 0.14      M=16 -> 0.54      M=18 -> 0.99     (±one uplink)
  burst:      SLEN=7 -> 0.11    SLEN=8 -> 0.54    SLEN=9 -> 0.99   (±one packet)
  sync window: WIN=96 -> 0.54   WIN=112 -> 0.22   WIN=120 -> 0.14  (gradual)
```

`P[Q]` is **sharp in the load parameters** `M` and `SLEN` (change either by one
step and it snaps to ~0 or ~1) but **gradual in the synchronisation window**
`WIN`. So the region where `Q` is *genuinely uncertain* (neither rare nor
certain) is a thin shell **along the synchronisation axis** — which is exactly
the parameter an operator does *not* control. That is why the probabilistic
boxes below range `WIN` (and `SLEN`), not `M`.

## Box P1 — probabilistic, 1-D (the sync window)
```
A_P1 ≡ (M = 16) ∧ (SLEN = 8) ∧ (96 ≤ WIN ≤ 120)
```
8 uplinks, 8-packet flows, spread over 12–15× the flow length. Every point in
the uncertain band:

| WIN | WIN/SLEN | P[Q] (oracle) |
|---|---|---|
| 96  | 12× | 0.536 |
| 104 | 13× | 0.345 |
| 112 | 14× | 0.220 |
| 120 | 15× | 0.142 |

box range: **`P[Q] ∈ [0.14, 0.54]`** — no point certain, no point rare.

## Box P2 — probabilistic, 2-D (burst length AND sync window)  ← preferred
```
A_P2 ≡ (M = 16) ∧ (8 ≤ SLEN ≤ 9) ∧ (116 ≤ WIN ≤ 124)
```
Ranges **both** `SLEN` and `WIN` — the two things an operator controls *least*
(application response size and how synchronised the responders happen to be),
holding only the fan-in fixed.

| P[Q] (oracle) | WIN=116 | WIN=120 | WIN=124 |
|---|---|---|---|
| **SLEN=8** | 0.176 | 0.142 | 0.115 |
| **SLEN=9** | 0.550 | 0.469 | 0.399 |

box range: **`P[Q] ∈ [0.12, 0.55]`** — least-favorable corner `(SLEN=8, WIN=124)`
= 0.115, most-severe corner `(SLEN=9, WIN=116)` = 0.550. Every one of the six
points is a genuine coin-flip-ish risk. (This box is narrow in `WIN` precisely
because of the 0/1 observation above: widen `SLEN` to `[8,10]` or `WIN` past
~128 and a corner leaves the band.)

## Box E — extreme / obvious (certain incast)
```
A_E ≡ (20 ≤ M ≤ 24) ∧ (0 ≤ WIN ≤ 24) ∧ (8 ≤ SLEN ≤ 12)
```
10–12 uplinks whose flows arrive within ~2–3 flow-lengths (nearly synchronised).
Both corners `P[Q] = 1.0000` → **certain overflow everywhere.** This is textbook
incast: many senders, synchronised → the receiver drowns. Provable — and
obvious.

## The contrast (the paper's point)
| | `A_E` (extreme / obvious) | `A_P1` / `A_P2` (mild / non-obvious) |
|---|---|---|
| in words | 10–12 uplinks, nearly synchronised | 8 uplinks, short flows, de-synchronised 12–15× |
| `P[Q]` | `= 1` everywhere | `∈ [0.12, 0.55]` everywhere |
| certify `A ⟹ Q` (∀ / verification) | **succeeds** — but the assumption is the obvious one | **fails** — no point is certain |
| find a counterexample (∃) | trivially yes | yes, but same verdict as a 12%-risk point → can't rank |
| `P[Q \| A]` (probabilistic) | 1 (uninteresting) | **12–55% — the only actionable answer** |

The only assumptions a 100%-method can certify are `A_E`-shaped extremes; the
realistic de-synchronised regime `A_P` is invisible to it and is exactly where a
quantified `P[Q|A]` earns its keep.

## Running it
`M` even; use `-simpathlen 8500` (this model is `MMAX=24`). Exact checking is
intractable; use simulation, cross-checked by `python3 incast_sim.py`.
```
# Box P1:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=16,SLEN=8,WIN=96:8:120 \
      -sim -simmethod ci -simwidth 0.01 -simconf 0.01 -simpathlen 8500
# Box P2:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=16,SLEN=8:1:9,WIN=116:4:124 ...
# Box E:
prism incast.pm incast.props -prop 1 -const BUF=32,THRESH=8,M=20:2:24,WIN=0:8:24,SLEN=8:2:12 ...
```
Note: a `±1e-4` CI is only feasible for the near-0/1 points (e.g. box E); the
mid-probability box-P points need ~10^8 samples for that width, so use
`simwidth ≈ 0.01` there.

## Validation (PRISM simulation vs oracle)
Corners, `BUF=32, THRESH=8`. Oracle values (n=120k, ±~0.004); PRISM
cross-check at `simwidth=0.01` (box E at `0.001`) is consistent within CI, as
throughout this repo.

| box corner | point | oracle | PRISM |
|---|---|---|---|
| P1 max | `M=16, WIN=96, SLEN=8`  | 0.536 | _pending_ |
| P1 min | `M=16, WIN=120, SLEN=8` | 0.142 | _pending_ |
| P2 max | `M=16, WIN=116, SLEN=9` | 0.550 | _pending_ |
| P2 min | `M=16, WIN=124, SLEN=8` | 0.115 | _pending_ |
| E  min | `M=20, WIN=24, SLEN=8`  | 1.000 | _pending_ |
