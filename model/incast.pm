// =====================================================================
//  Top-of-rack (ToR) switch during INCAST  --  shared-buffer contention
// =====================================================================
//
//  We model the ToR switch in front of the receiver where incast happens.
//  One OUTPUT port feeds the receiver; several INPUT ports feed the switch.
//
//      in-rack server 1 --->[ q1 ]--.
//      in-rack server 2 --->[ q2 ]--+\                         .--------.
//        uplink 1 (2 flows) ->[ q3 ]-+\  (switch fabric)       | output |
//        uplink 2 (2 flows) ->[ q4 ]--+----------------------->|  qo    |--> receiver
//        uplink 3 (2 flows) ->[ q5 ]-+/                        '--------'
//        uplink 4 (2 flows) ->[ q6 ]-/
//
//   * The OUTPUT port drains 1 packet/slot to the receiver.
//   * One buffer per input port; EVERY buffer (inputs and output) has the
//     same capacity BUF.
//   * Every input port forwards at most 1 packet/slot into the output buffer.
//   * Input ports:
//       - 2 SERVER ports (q1,q2): one in-rack sender each (always present).
//       - 4 UPLINK ports (q3..q6): each aggregates 2 out-of-rack flows
//         (traffic via higher-layer switches). The FAN-OUT FANOUT = how many of
//         these uplinks actually carry traffic (only uplinks 1..FANOUT are active).
//
//   Each sender (server or uplink flow) independently picks a start slot
//   uniformly in [0..WIN] (the synchronization window) and then sends SLEN
//   packets back-to-back, one per slot.
//
//   Bad event Q : "at least THRESH packets are dropped at the OUTPUT buffer"
//                 (receiver-facing incast loss). Input drops are tracked too.
//
//   WIN, SLEN, BUF, THRESH and the fan-out FANOUT are left undefined so they can be
//   SWEPT over ranges (PRISM experiments). The "assumption" A we look for is a
//   *range* of these parameters -- e.g. a region of the (FANOUT, WIN) plane.
//   Example:  -const SLEN=3,BUF=5,THRESH=3,FANOUT=2,WIN=2:2:30
//
//   Uniform start without WIN-many branches: a still-waiting sender starts in
//   the current slot with probability 1/(WIN+1-slot). Conditioned on not having
//   started yet this makes the start slot exactly uniform on [0..WIN] (forced
//   to start at slot WIN, where the probability is 1).

dtmc

const int WIN;      // synchronization window: start slot in [0..WIN]   (>=1)
const int SLEN;     // packets per sender (back-to-back, 1 per slot)
const int BUF;      // buffer capacity (same for every port)
const int THRESH;   // bad event Q: at least THRESH packets dropped at the output
const int FANOUT;        // fan-out: number of active uplink ports, 0..4

const int N = 10;                  // sender slots (2 servers + 4 uplinks x 2 flows)
const int CAP = N * SLEN;          // an upper bound on how many can ever drop
const int HORIZON = WIN + N*SLEN + SLEN;  // by here all packets have arrived/drained
const int NSTAGE = N + 1;          // N start-substages + 1 service substage

// probability a still-waiting sender starts in THIS slot (uniform start on [0..WIN])
formula hz = 1.0 / (WIN + 1 - slot);

// A sender is "active" while it is still sending: started, and fewer than SLEN
// slots have elapsed since its start slot.
formula act_a1 = (a1_on=1 & slot-a1_t<SLEN) ? 1 : 0;   // server   -> q1
formula act_a2 = (a2_on=1 & slot-a2_t<SLEN) ? 1 : 0;   // server   -> q2
formula act_b1 = (b1_on=1 & slot-b1_t<SLEN) ? 1 : 0;   // uplink 1 -> q3
formula act_b2 = (b2_on=1 & slot-b2_t<SLEN) ? 1 : 0;
formula act_b3 = (b3_on=1 & slot-b3_t<SLEN) ? 1 : 0;   // uplink 2 -> q4
formula act_b4 = (b4_on=1 & slot-b4_t<SLEN) ? 1 : 0;
formula act_c1 = (c1_on=1 & slot-c1_t<SLEN) ? 1 : 0;   // uplink 3 -> q5
formula act_c2 = (c2_on=1 & slot-c2_t<SLEN) ? 1 : 0;
formula act_c3 = (c3_on=1 & slot-c3_t<SLEN) ? 1 : 0;   // uplink 4 -> q6
formula act_c4 = (c4_on=1 & slot-c4_t<SLEN) ? 1 : 0;

// arrivals into each input port this slot = number of its active senders
formula arr1 = act_a1;                 // server port q1
formula arr2 = act_a2;                 // server port q2
formula arr3 = act_b1 + act_b2;        // uplink port q3 (active iff FANOUT>=1)
formula arr4 = act_b3 + act_b4;        // uplink port q4 (active iff FANOUT>=2)
formula arr5 = act_c1 + act_c2;        // uplink port q5 (active iff FANOUT>=3)
formula arr6 = act_c3 + act_c4;        // uplink port q6 (active iff FANOUT>=4)

// ---------------------------------------------------------------------
//  Service for one slot. Order: (1) output drains 1 to the receiver,
//  (2) every backlogged input port forwards 1 into the output buffer
//      (overflow there = OUTPUT drops), (3) new arrivals enter the input
//      buffers (overflow there = INPUT drops). Everything below is a
//      function of the CURRENT state only.
// ---------------------------------------------------------------------
formula f1 = (q1>0) ? 1 : 0;
formula f2 = (q2>0) ? 1 : 0;
formula f3 = (q3>0) ? 1 : 0;
formula f4 = (q4>0) ? 1 : 0;
formula f5 = (q5>0) ? 1 : 0;
formula f6 = (q6>0) ? 1 : 0;
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
formula i_drop  = (arr1 - min(arr1, BUF - (q1 - f1)))
                + (arr2 - min(arr2, BUF - (q2 - f2)))
                + (arr3 - min(arr3, BUF - (q3 - f3)))
                + (arr4 - min(arr4, BUF - (q4 - f4)))
                + (arr5 - min(arr5, BUF - (q5 - f5)))
                + (arr6 - min(arr6, BUF - (q6 - f6)));

formula done = (slot = HORIZON);

module tor

    // --- per-sender state: "on" = has started, "_t" = the slot it started ---
    a1_on:[0..1] init 0;  a1_t:[0..WIN] init 0;     // server 1
    a2_on:[0..1] init 0;  a2_t:[0..WIN] init 0;     // server 2
    b1_on:[0..1] init 0;  b1_t:[0..WIN] init 0;     // uplink 1, flow a
    b2_on:[0..1] init 0;  b2_t:[0..WIN] init 0;     // uplink 1, flow b
    b3_on:[0..1] init 0;  b3_t:[0..WIN] init 0;     // uplink 2, flow a
    b4_on:[0..1] init 0;  b4_t:[0..WIN] init 0;     // uplink 2, flow b
    c1_on:[0..1] init 0;  c1_t:[0..WIN] init 0;     // uplink 3, flow a
    c2_on:[0..1] init 0;  c2_t:[0..WIN] init 0;     // uplink 3, flow b
    c3_on:[0..1] init 0;  c3_t:[0..WIN] init 0;     // uplink 4, flow a
    c4_on:[0..1] init 0;  c4_t:[0..WIN] init 0;     // uplink 4, flow b

    // --- buffers (all capacity BUF) ---
    q1:[0..BUF] init 0;  q2:[0..BUF] init 0;        // server input ports
    q3:[0..BUF] init 0;  q4:[0..BUF] init 0;        // uplink input ports
    q5:[0..BUF] init 0;  q6:[0..BUF] init 0;
    qo:[0..BUF] init 0;                             // output port (to receiver)

    // --- drop counters ---
    odrops:[0..CAP] init 0;   // dropped at the output  (the bad event is on this)
    idrops:[0..CAP] init 0;   // dropped at the input ports

    slot :[0..HORIZON] init 0;
    stage:[1..NSTAGE] init 1; // substages 1..N resolve sender starts; N+1 = service

    // --- substages 1..N: each still-waiting sender starts with prob hz --------
    //     (uplink flows only exist while their uplink is within the fan-out FANOUT)
    [] stage=1 & slot<HORIZON & a1_on=0 & slot<=WIN -> hz:(a1_on'=1)&(a1_t'=slot)&(stage'=2) + (1-hz):(stage'=2);
    [] stage=1 & slot<HORIZON & !(a1_on=0 & slot<=WIN) -> (stage'=2);
    [] stage=2 & slot<HORIZON & a2_on=0 & slot<=WIN -> hz:(a2_on'=1)&(a2_t'=slot)&(stage'=3) + (1-hz):(stage'=3);
    [] stage=2 & slot<HORIZON & !(a2_on=0 & slot<=WIN) -> (stage'=3);
    [] stage=3 & slot<HORIZON & b1_on=0 & slot<=WIN & FANOUT>=1 -> hz:(b1_on'=1)&(b1_t'=slot)&(stage'=4) + (1-hz):(stage'=4);
    [] stage=3 & slot<HORIZON & !(b1_on=0 & slot<=WIN & FANOUT>=1) -> (stage'=4);
    [] stage=4 & slot<HORIZON & b2_on=0 & slot<=WIN & FANOUT>=1 -> hz:(b2_on'=1)&(b2_t'=slot)&(stage'=5) + (1-hz):(stage'=5);
    [] stage=4 & slot<HORIZON & !(b2_on=0 & slot<=WIN & FANOUT>=1) -> (stage'=5);
    [] stage=5 & slot<HORIZON & b3_on=0 & slot<=WIN & FANOUT>=2 -> hz:(b3_on'=1)&(b3_t'=slot)&(stage'=6) + (1-hz):(stage'=6);
    [] stage=5 & slot<HORIZON & !(b3_on=0 & slot<=WIN & FANOUT>=2) -> (stage'=6);
    [] stage=6 & slot<HORIZON & b4_on=0 & slot<=WIN & FANOUT>=2 -> hz:(b4_on'=1)&(b4_t'=slot)&(stage'=7) + (1-hz):(stage'=7);
    [] stage=6 & slot<HORIZON & !(b4_on=0 & slot<=WIN & FANOUT>=2) -> (stage'=7);
    [] stage=7 & slot<HORIZON & c1_on=0 & slot<=WIN & FANOUT>=3 -> hz:(c1_on'=1)&(c1_t'=slot)&(stage'=8) + (1-hz):(stage'=8);
    [] stage=7 & slot<HORIZON & !(c1_on=0 & slot<=WIN & FANOUT>=3) -> (stage'=8);
    [] stage=8 & slot<HORIZON & c2_on=0 & slot<=WIN & FANOUT>=3 -> hz:(c2_on'=1)&(c2_t'=slot)&(stage'=9) + (1-hz):(stage'=9);
    [] stage=8 & slot<HORIZON & !(c2_on=0 & slot<=WIN & FANOUT>=3) -> (stage'=9);
    [] stage=9 & slot<HORIZON & c3_on=0 & slot<=WIN & FANOUT>=4 -> hz:(c3_on'=1)&(c3_t'=slot)&(stage'=10) + (1-hz):(stage'=10);
    [] stage=9 & slot<HORIZON & !(c3_on=0 & slot<=WIN & FANOUT>=4) -> (stage'=10);
    [] stage=10 & slot<HORIZON & c4_on=0 & slot<=WIN & FANOUT>=4 -> hz:(c4_on'=1)&(c4_t'=slot)&(stage'=11) + (1-hz):(stage'=11);
    [] stage=10 & slot<HORIZON & !(c4_on=0 & slot<=WIN & FANOUT>=4) -> (stage'=11);

    // --- substage N+1: serve one slot, tally drops, advance the clock --------
    [step] stage=NSTAGE & slot<HORIZON ->
          (q1'=q1_next) & (q2'=q2_next) & (q3'=q3_next)
        & (q4'=q4_next) & (q5'=q5_next) & (q6'=q6_next)
        & (qo'=qo_next)
        & (odrops'=min(CAP, odrops + o_drop))
        & (idrops'=min(CAP, idrops + i_drop))
        & (slot'=slot+1) & (stage'=1);

    // --- absorbing once the run is over -------------------------------------
    [end] slot=HORIZON -> (stage'=stage);

endmodule

label "done" = (slot = HORIZON);
