// =====================================================================
//  Top-of-rack (ToR) switch during INCAST  --  shared-buffer contention
// =====================================================================
//
//  We model the ToR switch in front of the receiver where incast happens.
//  One OUTPUT port feeds the receiver; the other ports are UPLINKS, each
//  aggregating MPP=2 out-of-rack flows (traffic via higher-layer switches).
//
//        uplink 1 (2 flows) ->[ q1 ]--.
//        uplink 2 (2 flows) ->[ q2 ]--+\                       .--------.
//        uplink 3 (2 flows) ->[ q3 ]--+ \  (switch fabric)     | output |
//        uplink 4 (2 flows) ->[ q4 ]--+ ----------------------->|  qo   |--> receiver
//        uplink 5 (2 flows) ->[ q5 ]--+ /                      '--------'
//        uplink 6 (2 flows) ->[ q6 ]--'
//
//   * The OUTPUT port drains 1 packet/slot to the receiver.
//   * One buffer per port; EVERY buffer (inputs and output) has capacity BUF.
//   * Every input port forwards at most 1 packet/slot into the output buffer.
//   * MPP = 2 flows per uplink is FIXED.  The single input-traffic knob is the
//     total number of senders M; the active ports are uplinks 1..M/2 (so the
//     fan-out is M/2).  M is even, 2..12.
//
//   Each sender (flow) independently picks a start slot uniformly in [0..WIN]
//   (the synchronization window) and then sends SLEN packets back-to-back, one
//   per slot.
//
//   Bad event Q : "at least THRESH packets dropped at the OUTPUT buffer"
//                 (receiver-facing incast loss).  Input drops are tracked too.
//
//   The INPUT-TRAFFIC parameters M, WIN, SLEN are left undefined so the
//   "assumption" A can be a RANGE (a box) over them, applying to every
//   combination inside it.  BUF (switch) and THRESH (severity of Q) are held
//   fixed at representative values.  Example assumption and sweep:
//       A = (M in [6..12]) & (WIN in [0..48]) & (SLEN in [16..24])
//       -const BUF=32,THRESH=8,M=6:2:12,WIN=0:8:48,SLEN=16:2:24
//
//   Uniform start without WIN-many branches: a still-waiting sender starts in
//   the current slot with probability 1/(WIN+1-slot); conditioned on not having
//   started yet this is exactly uniform on [0..WIN] (forced to start at WIN).

dtmc

const int M;       // TOTAL SENDERS (input-traffic knob); even, 2..12; fan-out = M/2
const int WIN;     // synchronization window: start slot in [0..WIN]   (>=1)
const int SLEN;    // packets per sender (back-to-back, 1 per slot)
const int BUF;     // buffer capacity (same for every port; representative)
const int THRESH;  // bad event Q: at least THRESH packets dropped at the output

const int MPP  = 2;            // flows per uplink (fixed)
const int MMAX = 12;           // sender slots modelled (= MPP * 6 uplink ports)
const int HORIZON = WIN + M*SLEN + SLEN;   // by here all packets arrived/drained
const int NSTAGE  = MMAX + 1;  // MMAX start-substages + 1 service substage
const int TWIN = max(WIN, 1);   // start-slot range bound (avoids a degenerate [0..0] at WIN=0)

formula hz = 1.0 / (WIN + 1 - slot);

// A sender is "active" while still sending: started, < SLEN slots since start.
formula a1 = (on1=1 & slot-t1<SLEN) ? 1 : 0;   formula a2 = (on2=1 & slot-t2<SLEN) ? 1 : 0;   // uplink 1
formula a3 = (on3=1 & slot-t3<SLEN) ? 1 : 0;   formula a4 = (on4=1 & slot-t4<SLEN) ? 1 : 0;   // uplink 2
formula a5 = (on5=1 & slot-t5<SLEN) ? 1 : 0;   formula a6 = (on6=1 & slot-t6<SLEN) ? 1 : 0;   // uplink 3
formula a7 = (on7=1 & slot-t7<SLEN) ? 1 : 0;   formula a8 = (on8=1 & slot-t8<SLEN) ? 1 : 0;   // uplink 4
formula a9 = (on9=1 & slot-t9<SLEN) ? 1 : 0;   formula a10= (on10=1 & slot-t10<SLEN) ? 1 : 0; // uplink 5
formula a11= (on11=1 & slot-t11<SLEN) ? 1 : 0; formula a12= (on12=1 & slot-t12<SLEN) ? 1 : 0; // uplink 6

// arrivals into each uplink port this slot = number of its active flows (0..2)
formula arr1 = a1 + a2;   formula arr2 = a3 + a4;   formula arr3 = a5 + a6;
formula arr4 = a7 + a8;   formula arr5 = a9 + a10;  formula arr6 = a11 + a12;

// ---------------------------------------------------------------------
//  Service for one slot. (1) output drains 1 to the receiver, (2) every
//  backlogged input port forwards 1 into the output (overflow = OUTPUT drops),
//  (3) arrivals enter the input buffers (overflow = INPUT drops). All
//  expressions are functions of the CURRENT state only.
// ---------------------------------------------------------------------
formula f1 = (q1>0)?1:0;  formula f2 = (q2>0)?1:0;  formula f3 = (q3>0)?1:0;
formula f4 = (q4>0)?1:0;  formula f5 = (q5>0)?1:0;  formula f6 = (q6>0)?1:0;
formula Ftot = f1 + f2 + f3 + f4 + f5 + f6;

formula o_drained = max(qo - 1, 0);
formula o_room    = BUF - o_drained;
formula o_adm     = min(Ftot, o_room);
formula o_drop    = Ftot - o_adm;           // receiver-facing incast loss this slot
formula qo_next   = o_drained + o_adm;

formula q1_next = (q1 - f1) + min(arr1, BUF - (q1 - f1));
formula q2_next = (q2 - f2) + min(arr2, BUF - (q2 - f2));
formula q3_next = (q3 - f3) + min(arr3, BUF - (q3 - f3));
formula q4_next = (q4 - f4) + min(arr4, BUF - (q4 - f4));
formula q5_next = (q5 - f5) + min(arr5, BUF - (q5 - f5));
formula q6_next = (q6 - f6) + min(arr6, BUF - (q6 - f6));
formula i_drop  = (arr1 - min(arr1, BUF - (q1 - f1))) + (arr2 - min(arr2, BUF - (q2 - f2)))
                + (arr3 - min(arr3, BUF - (q3 - f3))) + (arr4 - min(arr4, BUF - (q4 - f4)))
                + (arr5 - min(arr5, BUF - (q5 - f5))) + (arr6 - min(arr6, BUF - (q6 - f6)));

formula done = (slot = HORIZON);

module tor

    // --- per-sender state: on_k = started?, t_k = start slot. Sender k belongs
    //     to uplink ceil(k/2); it only ever starts if k <= M (else its port is
    //     outside the fan-out and stays idle). ---
    on1 :[0..1] init 0; t1 :[0..TWIN] init 0;   on2 :[0..1] init 0; t2 :[0..TWIN] init 0;
    on3 :[0..1] init 0; t3 :[0..TWIN] init 0;   on4 :[0..1] init 0; t4 :[0..TWIN] init 0;
    on5 :[0..1] init 0; t5 :[0..TWIN] init 0;   on6 :[0..1] init 0; t6 :[0..TWIN] init 0;
    on7 :[0..1] init 0; t7 :[0..TWIN] init 0;   on8 :[0..1] init 0; t8 :[0..TWIN] init 0;
    on9 :[0..1] init 0; t9 :[0..TWIN] init 0;   on10:[0..1] init 0; t10:[0..TWIN] init 0;
    on11:[0..1] init 0; t11:[0..TWIN] init 0;   on12:[0..1] init 0; t12:[0..TWIN] init 0;

    // --- buffers (all capacity BUF) ---
    q1:[0..BUF] init 0; q2:[0..BUF] init 0; q3:[0..BUF] init 0;
    q4:[0..BUF] init 0; q5:[0..BUF] init 0; q6:[0..BUF] init 0;
    qo:[0..BUF] init 0;                                 // output port (to receiver)

    // --- drop counters (capped at THRESH; once Q holds it stays) ---
    odrops:[0..THRESH] init 0;   // dropped at the output  (the bad event is on this)
    idrops:[0..THRESH] init 0;   // dropped at the input ports

    slot :[0..HORIZON] init 0;
    stage:[1..NSTAGE] init 1;    // substages 1..MMAX resolve starts; MMAX+1 = service

    // --- substages 1..MMAX: each still-waiting, in-fan-out sender starts w/ prob hz
    [] stage=1  & slot<HORIZON & 1<=M  & on1=0  & slot<=WIN -> hz:(on1'=1)&(t1'=slot)&(stage'=2)  + (1-hz):(stage'=2);
    [] stage=1  & slot<HORIZON & !(1<=M  & on1=0  & slot<=WIN) -> (stage'=2);
    [] stage=2  & slot<HORIZON & 2<=M  & on2=0  & slot<=WIN -> hz:(on2'=1)&(t2'=slot)&(stage'=3)  + (1-hz):(stage'=3);
    [] stage=2  & slot<HORIZON & !(2<=M  & on2=0  & slot<=WIN) -> (stage'=3);
    [] stage=3  & slot<HORIZON & 3<=M  & on3=0  & slot<=WIN -> hz:(on3'=1)&(t3'=slot)&(stage'=4)  + (1-hz):(stage'=4);
    [] stage=3  & slot<HORIZON & !(3<=M  & on3=0  & slot<=WIN) -> (stage'=4);
    [] stage=4  & slot<HORIZON & 4<=M  & on4=0  & slot<=WIN -> hz:(on4'=1)&(t4'=slot)&(stage'=5)  + (1-hz):(stage'=5);
    [] stage=4  & slot<HORIZON & !(4<=M  & on4=0  & slot<=WIN) -> (stage'=5);
    [] stage=5  & slot<HORIZON & 5<=M  & on5=0  & slot<=WIN -> hz:(on5'=1)&(t5'=slot)&(stage'=6)  + (1-hz):(stage'=6);
    [] stage=5  & slot<HORIZON & !(5<=M  & on5=0  & slot<=WIN) -> (stage'=6);
    [] stage=6  & slot<HORIZON & 6<=M  & on6=0  & slot<=WIN -> hz:(on6'=1)&(t6'=slot)&(stage'=7)  + (1-hz):(stage'=7);
    [] stage=6  & slot<HORIZON & !(6<=M  & on6=0  & slot<=WIN) -> (stage'=7);
    [] stage=7  & slot<HORIZON & 7<=M  & on7=0  & slot<=WIN -> hz:(on7'=1)&(t7'=slot)&(stage'=8)  + (1-hz):(stage'=8);
    [] stage=7  & slot<HORIZON & !(7<=M  & on7=0  & slot<=WIN) -> (stage'=8);
    [] stage=8  & slot<HORIZON & 8<=M  & on8=0  & slot<=WIN -> hz:(on8'=1)&(t8'=slot)&(stage'=9)  + (1-hz):(stage'=9);
    [] stage=8  & slot<HORIZON & !(8<=M  & on8=0  & slot<=WIN) -> (stage'=9);
    [] stage=9  & slot<HORIZON & 9<=M  & on9=0  & slot<=WIN -> hz:(on9'=1)&(t9'=slot)&(stage'=10) + (1-hz):(stage'=10);
    [] stage=9  & slot<HORIZON & !(9<=M  & on9=0  & slot<=WIN) -> (stage'=10);
    [] stage=10 & slot<HORIZON & 10<=M & on10=0 & slot<=WIN -> hz:(on10'=1)&(t10'=slot)&(stage'=11) + (1-hz):(stage'=11);
    [] stage=10 & slot<HORIZON & !(10<=M & on10=0 & slot<=WIN) -> (stage'=11);
    [] stage=11 & slot<HORIZON & 11<=M & on11=0 & slot<=WIN -> hz:(on11'=1)&(t11'=slot)&(stage'=12) + (1-hz):(stage'=12);
    [] stage=11 & slot<HORIZON & !(11<=M & on11=0 & slot<=WIN) -> (stage'=12);
    [] stage=12 & slot<HORIZON & 12<=M & on12=0 & slot<=WIN -> hz:(on12'=1)&(t12'=slot)&(stage'=13) + (1-hz):(stage'=13);
    [] stage=12 & slot<HORIZON & !(12<=M & on12=0 & slot<=WIN) -> (stage'=13);

    // --- substage MMAX+1: serve one slot, tally drops, advance the clock ------
    [step] stage=NSTAGE & slot<HORIZON ->
          (q1'=q1_next) & (q2'=q2_next) & (q3'=q3_next)
        & (q4'=q4_next) & (q5'=q5_next) & (q6'=q6_next)
        & (qo'=qo_next)
        & (odrops'=min(THRESH, odrops + o_drop))
        & (idrops'=min(THRESH, idrops + i_drop))
        & (slot'=slot+1) & (stage'=1);

    // --- absorbing once the run is over -------------------------------------
    [end] slot=HORIZON -> (stage'=stage);

endmodule

label "done" = (slot = HORIZON);
