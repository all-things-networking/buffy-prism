"""Generate an all-uplink incast PRISM model for a given number of sender slots.
Same dynamics as example 1, parameterised by MMAX (even). MPP=2 flows/uplink."""
import sys

def gen(MMAX):
    MPP = 2
    PORTS = MMAX // MPP
    L = []
    A = L.append
    A("// =====================================================================")
    A("//  Top-of-rack (ToR) switch during INCAST  --  shared-buffer contention")
    A("//  (all-uplink variant; auto-generated for MMAX=%d senders, %d uplinks)" % (MMAX, PORTS))
    A("// =====================================================================")
    A("//")
    A("//  One OUTPUT port feeds the receiver (drains 1 packet/slot). Every other")
    A("//  port is an UPLINK carrying MPP=2 out-of-rack flows, one buffer each, all")
    A("//  of capacity BUF; every input port forwards at most 1 packet/slot to the")
    A("//  output. The single input-traffic knob is M = total senders; the active")
    A("//  uplinks are 1..M/2. Each sender picks a uniform start in [0..WIN] and")
    A("//  sends SLEN packets back-to-back. Bad event Q: >= THRESH drops at output.")
    A("//")
    A("//  M, WIN, SLEN are the input-traffic parameters swept as a range (a box);")
    A("//  BUF and THRESH are held fixed. Uniform start via the per-slot hazard")
    A("//  1/(WIN+1-slot).")
    A("")
    A("dtmc")
    A("")
    A("const int M;       // TOTAL SENDERS (input-traffic knob); even, 2..%d; fan-out = M/2" % MMAX)
    A("const int WIN;     // synchronization window: start slot in [0..WIN]")
    A("const int SLEN;    // packets per sender (back-to-back, 1 per slot)")
    A("const int BUF;     // buffer capacity (same for every port; representative)")
    A("const int THRESH;  // bad event Q: at least THRESH packets dropped at the output")
    A("")
    A("const int MPP  = %d;" % MPP)
    A("const int MMAX = %d;           // sender slots modelled (= MPP * %d uplink ports)" % (MMAX, PORTS))
    A("const int HORIZON = WIN + M*SLEN + SLEN;   // by here all packets arrived/drained")
    A("const int NSTAGE  = MMAX + 1;  // MMAX start-substages + 1 service substage")
    A("const int TWIN = max(WIN, 1);  // start-slot range bound (avoids [0..0] at WIN=0)")
    A("")
    A("formula hz = 1.0 / (WIN + 1 - slot);")
    A("")
    A("// active flows: started, and < SLEN slots since start")
    for k in range(1, MMAX + 1):
        A("formula a%d = (on%d=1 & slot-t%d<SLEN) ? 1 : 0;" % (k, k, k))
    A("")
    A("// arrivals into each uplink port = number of its active flows (0..MPP)")
    for j in range(1, PORTS + 1):
        A("formula arr%d = a%d + a%d;" % (j, 2*j-1, 2*j))
    A("")
    A("// forwarding: a backlogged input port sends 1 to the output")
    for j in range(1, PORTS + 1):
        A("formula f%d = (q%d>0)?1:0;" % (j, j))
    A("formula Ftot = " + " + ".join("f%d" % j for j in range(1, PORTS + 1)) + ";")
    A("")
    A("formula o_drained = max(qo - 1, 0);")
    A("formula o_room    = BUF - o_drained;")
    A("formula o_adm     = min(Ftot, o_room);")
    A("formula o_drop    = Ftot - o_adm;          // receiver-facing incast loss this slot")
    A("formula qo_next   = o_drained + o_adm;")
    A("")
    for j in range(1, PORTS + 1):
        A("formula q%d_next = (q%d - f%d) + min(arr%d, BUF - (q%d - f%d));" % (j, j, j, j, j, j))
    A("formula i_drop = " + " + ".join(
        "(arr%d - min(arr%d, BUF - (q%d - f%d)))" % (j, j, j, j) for j in range(1, PORTS + 1)) + ";")
    A("")
    A("formula done = (slot = HORIZON);")
    A("")
    A("module tor")
    A("")
    A("    // per-sender state: on_k = started?, t_k = start slot; sender k is on")
    A("    // uplink ceil(k/2) and only starts if k <= M.")
    for k in range(1, MMAX + 1):
        A("    on%d:[0..1] init 0; t%d:[0..TWIN] init 0;" % (k, k))
    A("")
    for j in range(1, PORTS + 1):
        A("    q%d:[0..BUF] init 0;" % j)
    A("    qo:[0..BUF] init 0;")
    A("")
    A("    odrops:[0..THRESH] init 0;   // dropped at the output (the bad event)")
    A("    idrops:[0..THRESH] init 0;   // dropped at the input ports")
    A("")
    A("    slot :[0..HORIZON] init 0;")
    A("    stage:[1..NSTAGE] init 1;")
    A("")
    A("    // substages 1..MMAX: each still-waiting, in-fan-out sender starts w/ prob hz")
    for k in range(1, MMAX + 1):
        nxt = k + 1
        A("    [] stage=%d & slot<HORIZON & %d<=M & on%d=0 & slot<=WIN -> hz:(on%d'=1)&(t%d'=slot)&(stage'=%d) + (1-hz):(stage'=%d);"
          % (k, k, k, k, k, nxt, nxt))
        A("    [] stage=%d & slot<HORIZON & !(%d<=M & on%d=0 & slot<=WIN) -> (stage'=%d);"
          % (k, k, k, nxt))
    A("")
    A("    // substage MMAX+1: serve one slot, tally drops, advance the clock")
    qupd = " & ".join("(q%d'=q%d_next)" % (j, j) for j in range(1, PORTS + 1))
    A("    [step] stage=NSTAGE & slot<HORIZON ->")
    A("          " + qupd)
    A("        & (qo'=qo_next)")
    A("        & (odrops'=min(THRESH, odrops + o_drop))")
    A("        & (idrops'=min(THRESH, idrops + i_drop))")
    A("        & (slot'=slot+1) & (stage'=1);")
    A("")
    A("    [end] slot=HORIZON -> (stage'=stage);")
    A("")
    A("endmodule")
    A("")
    A('label "done" = (slot = HORIZON);')
    return "\n".join(L) + "\n"

if __name__ == "__main__":
    mmax = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    sys.stdout.write(gen(mmax))
