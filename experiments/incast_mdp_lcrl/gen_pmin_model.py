"""Generate incast_pmin_mdp.pm from incast_mdp.pm: move start-time selection to
an initial nondeterministic phase (each in-fanout sender's t_k chosen in
[0..WIN], forced to start), so 'never send' is impossible and Pmin is physical."""
import os, re
SRC = "models/example2_desync_short_bursts/incast_mdp.pm"
DST = "models/example2_desync_short_bursts/incast_pmin_mdp.pm"
MMAX = 20
lines = open(SRC).read().splitlines()

def slice_verbatim(start_pred, end_pred):
    out, on = [], False
    for ln in lines:
        if not on and start_pred(ln): on = True
        if on: out.append(ln)
        if on and end_pred(ln): break
    return out

# exact arrival/forwarding/service formulas (arr1 .. i_drop), reused verbatim
formulas = slice_verbatim(lambda l: l.startswith("formula arr1"),
                          lambda l: l.startswith("formula i_drop"))
assert formulas and formulas[-1].startswith("formula i_drop"), "formula block not found"

# active-flow formulas, FIXED to require slot>=t_k (t_k may now be a future slot)
active = []
for k in range(1, MMAX+1):
    active.append(f"formula a{k} = (on{k}=1 & slot>=t{k} & slot-t{k}<SLEN) ? 1 : 0;")

# per-sender variable declarations
decls = []
for k in range(1, MMAX+1):
    decls.append(f"    on{k}:[0..1] init 0; t{k}:[0..TWIN] init 0;")
qdecls = "\n".join(f"    q{j}:[0..BUF] init 0;" for j in range(1, 11))

# INIT phase: for sender k, either increment its start slot or commit (start at t_k).
# k>M senders are skipped (stay idle, on_k=0).
init = []
for k in range(1, MMAX+1):
    init.append(f"    // sender {k}: choose start slot t{k} in [0..WIN], then commit")
    init.append(f"    [] mode=0 & istage={k} & {k}<=M & t{k}<WIN -> (t{k}'=t{k}+1);")
    init.append(f"    [] mode=0 & istage={k} & {k}<=M           -> (on{k}'=1) & (istage'={k+1});")
    init.append(f"    [] mode=0 & istage={k} & !({k}<=M)         -> (istage'={k+1});")
init.append(f"    [] mode=0 & istage={MMAX+1} -> (mode'=1);   // schedule fixed; begin the run")

qn = " & ".join(f"(q{j}'=q{j}_next)" for j in range(1, 11))

model = f"""// =====================================================================
//  ToR incast  --  MDP variant for Pmin (each sender MUST start within WIN)
//  (auto-generated from incast_mdp.pm; MMAX={MMAX} senders, 10 uplinks)
// =====================================================================
//
//  Difference vs incast_mdp.pm: instead of a per-slot start-vs-wait choice
//  (which lets a scheduler avoid loss by never sending), the start slot t_k of
//  every in-fan-out sender (k<=M) is chosen NONDETERMINISTICALLY in [0..WIN] in
//  an initial scheduling phase (mode=0), and the sender is forced to start
//  (on_k=1). The run (mode=1) is then a deterministic per-slot service, so the
//  only nondeterminism is the schedule. Pmax = worst-case schedule, Pmin =
//  best-case schedule -- but always with all M senders sending, so Pmin is
//  physically meaningful (no never-send escape).

mdp

const int M;       // TOTAL SENDERS (input-traffic knob); even, 2..20; fan-out = M/2
const int WIN;     // synchronization window: start slot chosen in [0..WIN]
const int SLEN;    // packets per sender (back-to-back, 1 per slot)
const int BUF;     // buffer capacity (same for every port; representative)
const int THRESH;  // bad event Q: at least THRESH packets dropped at the output

const int MPP  = 2;
const int MMAX = {MMAX};           // sender slots modelled (= MPP * 10 uplink ports)
const int HORIZON = WIN + M*SLEN + SLEN;   // by here all packets arrived/drained
const int TWIN = max(WIN, 1);  // start-slot range bound (avoids [0..0] at WIN=0)

// active flows: scheduled (on=1), started (slot>=t), and < SLEN slots since start
{chr(10).join(active)}

{chr(10).join(formulas)}

module tor

    // per-sender state: on_k = scheduled-to-send?, t_k = chosen start slot
{chr(10).join(decls)}

{qdecls}
    qo:[0..BUF] init 0;

    odrops:[0..THRESH] init 0;   // dropped at the output (the bad event)
    idrops:[0..THRESH] init 0;   // dropped at the input ports

    slot :[0..HORIZON] init 0;
    mode :[0..1] init 0;          // 0 = choose the schedule, 1 = run it
    istage:[1..{MMAX+1}] init 1;  // which sender is being scheduled (mode=0)

    // ---- scheduling phase: fix every in-fan-out sender's start slot ----
{chr(10).join(init)}

    // ---- run phase: one deterministic service step per slot ----
    [step] mode=1 & slot<HORIZON ->
          {qn}
        & (qo'=qo_next)
        & (odrops'=min(THRESH, odrops + o_drop))
        & (idrops'=min(THRESH, idrops + i_drop))
        & (slot'=slot+1);

    [end] mode=1 & slot=HORIZON -> (slot'=slot);

endmodule

label "done" = (slot = HORIZON);
"""
open(DST, "w").write(model)
print("wrote", DST, "(%d lines)" % (model.count(chr(10))+1))
