# Summary: the case studies, and what the compiler work enabled (2026-11-11)

Details: `draft/case-studies-intro.md` (§2–§8), the per-study notes `docs/notes/case-study-*.md`, and
design decisions 42–49 in `docs/notes/buffy-compiler-design-decisions.md`.

## What we found

| Study | Bad event | Main finding |
|---|---|---|
| **B. Buggy FQ** | the thin flow cuts ahead of the bulk flows 4+ times (the *bulk* flows starve) | Only the thin flow's timing matters: a quiet start, then single packets. At the sharpest condition, P(Q\|A) = 0.50 from a 1.2% base. A solver finds other workloads that trigger the bug, but they carry < 2·10⁻⁷ of its probability. The RFC 8290 fix removes it. |
| **C. LLM scheduler** | an interactive request waits ≥ 20 iterations | Long-output requests just ahead of it decide everything. A mild condition (6% of runs) gives 64%, a rare one (1.8%) gives 100%, and one that holds in 57% of runs rules it out. Shortest-job-first fixes it. |
| | the same request is evicted | It needs a long request ahead of it; without one it never happens. No simple condition makes it more than about a third likely. |
| **D. Loom NIC** | tenant 1 starved in a 20-step window | Unfair 18% of the time even when average shares are equal; at least 37% across a mild load box. The intended policy gives 0. |
| **E. TCP outcast** | the lone flow gets ≤ half its fair share | It happens with small buffers. Once the lone flow backs off it gets locked out (91%), and it recovers only through gaps in the other port's traffic (2%). RED fixes it. Sticky tie-breaking hurts it in the tail, not on average. |
| **F. PFC** | a flow that never touches the congested switch gets blocked | Happens only with PFC, and rarely (0.13%). No simple input pattern makes it likely; the hazard is diffuse. PFC actually *helps* the flow beside the congestion, whose real problem is head-of-line blocking. |

(Case study A, TCP incast, is unchanged from the draft: two mild boxes with P(Q) ≥ 0.54–0.64.)

The common thread: probabilities say things averages and "is this possible?" checks can't. Equal
average shares can still be unfair, as in D and E. A possible trigger can be negligible, as in B. And a
mild condition can make a rare event certain or impossible, as in C.

## What the recent compiler work enabled

- **Exact conditioning (`--condition-on`, design decision 49).** The rare conditions in B and C
  (P = 0.002 down to 5·10⁻⁷) became cheap to estimate: about 500× fewer runs, with P(A) exact instead
  of estimated. Before, "rare A" was the draft's stated open problem for B.
- **Factored LTL monitors (decision 48).** Learned conditions are combinations of time windows, which
  used to blow past the 100,000-state monitor limit. Outcast's conditions failed to compile before; now
  every case study's learned conditions compile as plain `given` queries.
- **Loop variables in draw conditions (decision 47).** This lets each sender's sending rate depend on
  its own state, which outcast's closed-loop TCP senders needed.
- **Earlier work (immediate connections, the native simulator, `--stop-at-horizon`; decisions 42–46).**
  Loom's multi-module network and the million-run studies were feasible because of these.
- **Learn, then certify.** The pipeline is now:
  1. record input histories at scale;
  2. learn temporal conditions;
  3. certify each on the compiled model with an exact P(A).

  That's what turned B and C from "preliminary" and "not yet validated" into finished studies.
  Certification also caught one learner error, in PFC.

## What it didn't fix

- Model-size limits are unchanged. Exact checking stops at about 2–3M states, and Z3 timed out on C's
  full-scale proofs.
- Conditioning handles one random source per condition, and gets slow when the conditioning input's
  state space is large (PFC). A table-lookup primitive in the native simulator would fix the latter.
