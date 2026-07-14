// =====================================================================
//  Top-of-rack (ToR) switch during INCAST  --  shared-buffer contention
//  (all-uplink variant; auto-generated for MMAX=20 senders, 10 uplinks)
// =====================================================================
//
//  One OUTPUT port feeds the receiver (drains 1 packet/slot). Every other
//  port is an UPLINK carrying MPP=2 out-of-rack flows, one buffer each, all
//  of capacity BUF; every input port forwards at most 1 packet/slot to the
//  output. The single input-traffic knob is M = total senders; the active
//  uplinks are 1..M/2. Each sender picks a uniform start in [0..WIN] and
//  sends SLEN packets back-to-back. Bad event Q: >= THRESH drops at output.
//
//  M, WIN, SLEN are the input-traffic parameters swept as a range (a box);
//  BUF and THRESH are held fixed. Uniform start via the per-slot hazard
//  1/(WIN+1-slot).

mdp

const int M;       // TOTAL SENDERS (input-traffic knob); even, 2..20; fan-out = M/2
const int WIN;     // synchronization window: start slot in [0..WIN]
const int SLEN;    // packets per sender (back-to-back, 1 per slot)
const int BUF;     // buffer capacity (same for every port; representative)
const int THRESH;  // bad event Q: at least THRESH packets dropped at the output

const int MPP  = 2;
const int MMAX = 20;           // sender slots modelled (= MPP * 10 uplink ports)
const int HORIZON = WIN + M*SLEN + SLEN;   // by here all packets arrived/drained
const int NSTAGE  = MMAX + 1;  // MMAX start-substages + 1 service substage
const int TWIN = max(WIN, 1);  // start-slot range bound (avoids [0..0] at WIN=0)

formula hz = 1.0 / (WIN + 1 - slot);

// active flows: started, and < SLEN slots since start
formula a1 = (on1=1 & slot-t1<SLEN) ? 1 : 0;
formula a2 = (on2=1 & slot-t2<SLEN) ? 1 : 0;
formula a3 = (on3=1 & slot-t3<SLEN) ? 1 : 0;
formula a4 = (on4=1 & slot-t4<SLEN) ? 1 : 0;
formula a5 = (on5=1 & slot-t5<SLEN) ? 1 : 0;
formula a6 = (on6=1 & slot-t6<SLEN) ? 1 : 0;
formula a7 = (on7=1 & slot-t7<SLEN) ? 1 : 0;
formula a8 = (on8=1 & slot-t8<SLEN) ? 1 : 0;
formula a9 = (on9=1 & slot-t9<SLEN) ? 1 : 0;
formula a10 = (on10=1 & slot-t10<SLEN) ? 1 : 0;
formula a11 = (on11=1 & slot-t11<SLEN) ? 1 : 0;
formula a12 = (on12=1 & slot-t12<SLEN) ? 1 : 0;
formula a13 = (on13=1 & slot-t13<SLEN) ? 1 : 0;
formula a14 = (on14=1 & slot-t14<SLEN) ? 1 : 0;
formula a15 = (on15=1 & slot-t15<SLEN) ? 1 : 0;
formula a16 = (on16=1 & slot-t16<SLEN) ? 1 : 0;
formula a17 = (on17=1 & slot-t17<SLEN) ? 1 : 0;
formula a18 = (on18=1 & slot-t18<SLEN) ? 1 : 0;
formula a19 = (on19=1 & slot-t19<SLEN) ? 1 : 0;
formula a20 = (on20=1 & slot-t20<SLEN) ? 1 : 0;

// arrivals into each uplink port = number of its active flows (0..MPP)
formula arr1 = a1 + a2;
formula arr2 = a3 + a4;
formula arr3 = a5 + a6;
formula arr4 = a7 + a8;
formula arr5 = a9 + a10;
formula arr6 = a11 + a12;
formula arr7 = a13 + a14;
formula arr8 = a15 + a16;
formula arr9 = a17 + a18;
formula arr10 = a19 + a20;

// forwarding: a backlogged input port sends 1 to the output
formula f1 = (q1>0)?1:0;
formula f2 = (q2>0)?1:0;
formula f3 = (q3>0)?1:0;
formula f4 = (q4>0)?1:0;
formula f5 = (q5>0)?1:0;
formula f6 = (q6>0)?1:0;
formula f7 = (q7>0)?1:0;
formula f8 = (q8>0)?1:0;
formula f9 = (q9>0)?1:0;
formula f10 = (q10>0)?1:0;
formula Ftot = f1 + f2 + f3 + f4 + f5 + f6 + f7 + f8 + f9 + f10;

formula o_drained = max(qo - 1, 0);
formula o_room    = BUF - o_drained;
formula o_adm     = min(Ftot, o_room);
formula o_drop    = Ftot - o_adm;          // receiver-facing incast loss this slot
formula qo_next   = o_drained + o_adm;

formula q1_next = (q1 - f1) + min(arr1, BUF - (q1 - f1));
formula q2_next = (q2 - f2) + min(arr2, BUF - (q2 - f2));
formula q3_next = (q3 - f3) + min(arr3, BUF - (q3 - f3));
formula q4_next = (q4 - f4) + min(arr4, BUF - (q4 - f4));
formula q5_next = (q5 - f5) + min(arr5, BUF - (q5 - f5));
formula q6_next = (q6 - f6) + min(arr6, BUF - (q6 - f6));
formula q7_next = (q7 - f7) + min(arr7, BUF - (q7 - f7));
formula q8_next = (q8 - f8) + min(arr8, BUF - (q8 - f8));
formula q9_next = (q9 - f9) + min(arr9, BUF - (q9 - f9));
formula q10_next = (q10 - f10) + min(arr10, BUF - (q10 - f10));
formula i_drop = (arr1 - min(arr1, BUF - (q1 - f1))) + (arr2 - min(arr2, BUF - (q2 - f2))) + (arr3 - min(arr3, BUF - (q3 - f3))) + (arr4 - min(arr4, BUF - (q4 - f4))) + (arr5 - min(arr5, BUF - (q5 - f5))) + (arr6 - min(arr6, BUF - (q6 - f6))) + (arr7 - min(arr7, BUF - (q7 - f7))) + (arr8 - min(arr8, BUF - (q8 - f8))) + (arr9 - min(arr9, BUF - (q9 - f9))) + (arr10 - min(arr10, BUF - (q10 - f10)));

formula done = (slot = HORIZON);

module tor

    // per-sender state: on_k = started?, t_k = start slot; sender k is on
    // uplink ceil(k/2) and only starts if k <= M.
    on1:[0..1] init 0; t1:[0..TWIN] init 0;
    on2:[0..1] init 0; t2:[0..TWIN] init 0;
    on3:[0..1] init 0; t3:[0..TWIN] init 0;
    on4:[0..1] init 0; t4:[0..TWIN] init 0;
    on5:[0..1] init 0; t5:[0..TWIN] init 0;
    on6:[0..1] init 0; t6:[0..TWIN] init 0;
    on7:[0..1] init 0; t7:[0..TWIN] init 0;
    on8:[0..1] init 0; t8:[0..TWIN] init 0;
    on9:[0..1] init 0; t9:[0..TWIN] init 0;
    on10:[0..1] init 0; t10:[0..TWIN] init 0;
    on11:[0..1] init 0; t11:[0..TWIN] init 0;
    on12:[0..1] init 0; t12:[0..TWIN] init 0;
    on13:[0..1] init 0; t13:[0..TWIN] init 0;
    on14:[0..1] init 0; t14:[0..TWIN] init 0;
    on15:[0..1] init 0; t15:[0..TWIN] init 0;
    on16:[0..1] init 0; t16:[0..TWIN] init 0;
    on17:[0..1] init 0; t17:[0..TWIN] init 0;
    on18:[0..1] init 0; t18:[0..TWIN] init 0;
    on19:[0..1] init 0; t19:[0..TWIN] init 0;
    on20:[0..1] init 0; t20:[0..TWIN] init 0;

    q1:[0..BUF] init 0;
    q2:[0..BUF] init 0;
    q3:[0..BUF] init 0;
    q4:[0..BUF] init 0;
    q5:[0..BUF] init 0;
    q6:[0..BUF] init 0;
    q7:[0..BUF] init 0;
    q8:[0..BUF] init 0;
    q9:[0..BUF] init 0;
    q10:[0..BUF] init 0;
    qo:[0..BUF] init 0;

    odrops:[0..THRESH] init 0;   // dropped at the output (the bad event)
    idrops:[0..THRESH] init 0;   // dropped at the input ports

    slot :[0..HORIZON] init 0;
    stage:[1..NSTAGE] init 1;

    // substages 1..MMAX: each still-waiting, in-fan-out sender starts w/ prob hz
    [start1] stage=1 & slot<HORIZON & 1<=M & on1=0 & slot<=WIN -> (on1'=1)&(t1'=slot)&(stage'=2);
    [cont1]  stage=1 & slot<HORIZON & 1<=M & on1=1 & slot<=WIN -> (stage'=2);
    [start2] stage=2 & slot<HORIZON & 2<=M & on2=0 & slot<=WIN -> (on2'=1)&(t2'=slot)&(stage'=3);
    [cont2]  stage=2 & slot<HORIZON & 2<=M & on2=1 & slot<=WIN -> (stage'=3);
    [start3] stage=3 & slot<HORIZON & 3<=M & on3=0 & slot<=WIN -> (on3'=1)&(t3'=slot)&(stage'=4);
    [cont3]  stage=3 & slot<HORIZON & 3<=M & on3=1 & slot<=WIN -> (stage'=4);
    [start4] stage=4 & slot<HORIZON & 4<=M & on4=0 & slot<=WIN -> (on4'=1)&(t4'=slot)&(stage'=5);
    [cont4]  stage=4 & slot<HORIZON & 4<=M & on4=1 & slot<=WIN -> (stage'=5);
    [start5] stage=5 & slot<HORIZON & 5<=M & on5=0 & slot<=WIN -> (on5'=1)&(t5'=slot)&(stage'=6);
    [cont5]  stage=5 & slot<HORIZON & 5<=M & on5=1 & slot<=WIN  -> (stage'=6);
    [start6] stage=6 & slot<HORIZON & 6<=M & on6=0 & slot<=WIN -> (on6'=1)&(t6'=slot)&(stage'=7);
    [cont6]  stage=6 & slot<HORIZON & 6<=M & on6=1 & slot<=WIN  -> (stage'=7);
    [start7] stage=7 & slot<HORIZON & 7<=M & on7=0 & slot<=WIN -> (on7'=1)&(t7'=slot)&(stage'=8);
    [cont7]  stage=7 & slot<HORIZON & 7<=M & on7=1 & slot<=WIN  -> (stage'=8);
    [start8] stage=8 & slot<HORIZON & 8<=M & on8=0 & slot<=WIN -> (on8'=1)&(t8'=slot)&(stage'=9);
    [cont8]  stage=8 & slot<HORIZON & 8<=M & on8=1 & slot<=WIN  -> (stage'=9);
    [start9] stage=9 & slot<HORIZON & 9<=M & on9=0 & slot<=WIN -> (on9'=1)&(t9'=slot)&(stage'=10);
    [cont9]  stage=9 & slot<HORIZON & 9<=M & on9=1 & slot<=WIN  -> (stage'=10);
    [start10] stage=10 & slot<HORIZON & 10<=M & on10=0 & slot<=WIN -> (on10'=1)&(t10'=slot)&(stage'=11);
    [cont10]  stage=10 & slot<HORIZON & 10<=M & on10=1 & slot<=WIN  -> (stage'=11);
    [start11] stage=11 & slot<HORIZON & 11<=M & on11=0 & slot<=WIN -> (on11'=1)&(t11'=slot)&(stage'=12);
    [cont11]  stage=11 & slot<HORIZON & 11<=M & on11=1 & slot<=WIN  -> (stage'=12);
    [start12] stage=12 & slot<HORIZON & 12<=M & on12=0 & slot<=WIN -> (on12'=1)&(t12'=slot)&(stage'=13);
    [cont12]  stage=12 & slot<HORIZON & 12<=M & on12=1 & slot<=WIN  -> (stage'=13);
    [start13] stage=13 & slot<HORIZON & 13<=M & on13=0 & slot<=WIN -> (on13'=1)&(t13'=slot)&(stage'=14);
    [cont13]  stage=13 & slot<HORIZON & 13<=M & on13=1 & slot<=WIN  -> (stage'=14);
    [start14] stage=14 & slot<HORIZON & 14<=M & on14=0 & slot<=WIN -> (on14'=1)&(t14'=slot)&(stage'=15);
    [cont14]  stage=14 & slot<HORIZON & 14<=M & on14=1 & slot<=WIN  -> (stage'=15);
    [start15] stage=15 & slot<HORIZON & 15<=M & on15=0 & slot<=WIN -> (on15'=1)&(t15'=slot)&(stage'=16);
    [cont15]  stage=15 & slot<HORIZON & 15<=M & on15=1 & slot<=WIN  -> (stage'=16);
    [start16] stage=16 & slot<HORIZON & 16<=M & on16=0 & slot<=WIN -> (on16'=1)&(t16'=slot)&(stage'=17);
    [cont16]  stage=16 & slot<HORIZON & 16<=M & on16=1 & slot<=WIN  -> (stage'=17);
    [start17] stage=17 & slot<HORIZON & 17<=M & on17=0 & slot<=WIN -> (on17'=1)&(t17'=slot)&(stage'=18);
    [cont17]  stage=17 & slot<HORIZON & 17<=M & on17=1 & slot<=WIN  -> (stage'=18);
    [start18] stage=18 & slot<HORIZON & 18<=M & on18=0 & slot<=WIN -> (on18'=1)&(t18'=slot)&(stage'=19);
    [cont18]  stage=18 & slot<HORIZON & 18<=M & on18=1 & slot<=WIN  -> (stage'=19);
    [start19] stage=19 & slot<HORIZON & 19<=M & on19=0 & slot<=WIN -> (on19'=1)&(t19'=slot)&(stage'=20);
    [cont19]  stage=19 & slot<HORIZON & 19<=M & on19=1 & slot<=WIN  -> (stage'=20);
    [start20] stage=20 & slot<HORIZON & 20<=M & on20=0 & slot<=WIN -> (on20'=1)&(t20'=slot)&(stage'=21);
    [cont20]  stage=20 & slot<HORIZON & 20<=M & on20=1 & slot<=WIN  -> (stage'=21);

    // substage MMAX+1: serve one slot, tally drops, advance the clock
    [step] stage=NSTAGE & slot<HORIZON ->
          (q1'=q1_next) & (q2'=q2_next) & (q3'=q3_next) & (q4'=q4_next) & (q5'=q5_next) & (q6'=q6_next) & (q7'=q7_next) & (q8'=q8_next) & (q9'=q9_next) & (q10'=q10_next)
        & (qo'=qo_next)
        & (odrops'=min(THRESH, odrops + o_drop))
        & (idrops'=min(THRESH, idrops + i_drop))
        & (slot'=slot+1) & (stage'=1);

    [end] slot=HORIZON -> (stage'=stage);

endmodule

label "done" = (slot = HORIZON);
