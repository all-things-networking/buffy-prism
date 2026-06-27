// Shared-buffer "incast" case study
// discrete time, probabilistic input (synchronization window)
// N senders -> 1 shared buffer
//
// Scenario:
//   - One buffer holds BUF packets, drained at SVC packets per time slot.
//   - N senders. Each sender independently picks a start slot uniformly in
//     [0..WIN] (the synchronization window) and then sends SLEN packets
//     back-to-back, one per slot.
//   - We do not want packet drops. The "bad event" Q is that at least
//     THRESH packets are dropped over the run (start with THRESH = 1).
//
// The model has two phases:
//   1. sampling: each sender draws its start slot (this fixes the INPUT).
//   2. running : the buffer is simulated slot-by-slot; arrivals each slot are
//                the senders currently transmitting, served then admitted,
//                with the overflow dropped.
//
// "peak" tracks the peak concurrency = peak offered load = the largest number
// of senders that are ever transmitting in the same slot. It is a function of
// the INPUT (start slots) alone, and equals the largest number of senders that
// start within any window of SLEN consecutive slots. We use it to phrase
// conditions A over the input in incast_buffer_conditional_queries.props.

dtmc

const int N = 5;          // number of senders
const int SLEN = 3;          // packets per sender (sent back-to-back, 1 per slot)
const int WIN = 8;          // synchronization window: start slot in [0..WIN]
const int BUF = 4;          // buffer capacity (packets)
const int SVC = 2;          // service rate (packets drained per slot)
const int THRESH = 1;     // bad event Q: at least THRESH packets dropped

const int HORIZON = WIN + SLEN;      // no sender is active beyond slot WIN+SLEN-1
const int DROP_CAP = N * SLEN;     // max packets that could ever be dropped
const double pstart = 1.0 / (WIN + 1);   // uniform prob. of each start slot

// --- arrivals this slot = senders currently transmitting ---
// sender i is active at the current slot iff starti <= slot < starti + SLEN
formula active = (start1<=slot & slot<start1+SLEN ? 1 : 0)
               + (start2<=slot & slot<start2+SLEN ? 1 : 0)
               + (start3<=slot & slot<start3+SLEN ? 1 : 0)
               + (start4<=slot & slot<start4+SLEN ? 1 : 0)
               + (start5<=slot & slot<start5+SLEN ? 1 : 0);

// --- buffer update for one slot: serve first, then admit, drop the overflow ---
formula departures = min(q, SVC);
formula room       = BUF - q + departures;     // free space after service
formula admitted   = min(active, room);
formula dropped    = active - admitted;
formula q_next     = q - departures + admitted;

formula running = (placed = N) & (slot < HORIZON);
formula done    = (placed = N) & (slot = HORIZON);

module incast

    // start slot chosen by each sender (the input); 0 until sampled
    start1 : [0..WIN] init 0;
    start2 : [0..WIN] init 0;
    start3 : [0..WIN] init 0;
    start4 : [0..WIN] init 0;
    start5 : [0..WIN] init 0;

    placed : [0..N] init 0;          // how many senders have drawn a start slot
    slot   : [0..HORIZON] init 0;    // current time slot during the run

    q     : [0..BUF] init 0;           // buffer occupancy
    drops : [0..DROP_CAP] init 0;    // total packets dropped so far
    peak  : [0..N] init 0;           // peak concurrency (peak offered load)

    // --- sampling phase: each sender draws its start slot uniformly in [0..WIN] ---
    [draw1] placed=0 ->
          pstart:(start1'=0)&(placed'=1) + pstart:(start1'=1)&(placed'=1)
        + pstart:(start1'=2)&(placed'=1) + pstart:(start1'=3)&(placed'=1)
        + pstart:(start1'=4)&(placed'=1) + pstart:(start1'=5)&(placed'=1)
        + pstart:(start1'=6)&(placed'=1) + pstart:(start1'=7)&(placed'=1)
        + pstart:(start1'=8)&(placed'=1);
    [draw2] placed=1 ->
          pstart:(start2'=0)&(placed'=2) + pstart:(start2'=1)&(placed'=2)
        + pstart:(start2'=2)&(placed'=2) + pstart:(start2'=3)&(placed'=2)
        + pstart:(start2'=4)&(placed'=2) + pstart:(start2'=5)&(placed'=2)
        + pstart:(start2'=6)&(placed'=2) + pstart:(start2'=7)&(placed'=2)
        + pstart:(start2'=8)&(placed'=2);
    [draw3] placed=2 ->
          pstart:(start3'=0)&(placed'=3) + pstart:(start3'=1)&(placed'=3)
        + pstart:(start3'=2)&(placed'=3) + pstart:(start3'=3)&(placed'=3)
        + pstart:(start3'=4)&(placed'=3) + pstart:(start3'=5)&(placed'=3)
        + pstart:(start3'=6)&(placed'=3) + pstart:(start3'=7)&(placed'=3)
        + pstart:(start3'=8)&(placed'=3);
    [draw4] placed=3 ->
          pstart:(start4'=0)&(placed'=4) + pstart:(start4'=1)&(placed'=4)
        + pstart:(start4'=2)&(placed'=4) + pstart:(start4'=3)&(placed'=4)
        + pstart:(start4'=4)&(placed'=4) + pstart:(start4'=5)&(placed'=4)
        + pstart:(start4'=6)&(placed'=4) + pstart:(start4'=7)&(placed'=4)
        + pstart:(start4'=8)&(placed'=4);
    [draw5] placed=4 ->
          pstart:(start5'=0)&(placed'=5) + pstart:(start5'=1)&(placed'=5)
        + pstart:(start5'=2)&(placed'=5) + pstart:(start5'=3)&(placed'=5)
        + pstart:(start5'=4)&(placed'=5) + pstart:(start5'=5)&(placed'=5)
        + pstart:(start5'=6)&(placed'=5) + pstart:(start5'=7)&(placed'=5)
        + pstart:(start5'=8)&(placed'=5);

    // --- running phase: advance one slot, updating buffer / drops / peak ---
    [step] running ->
        (q'=q_next)
      & (drops'=min(DROP_CAP, drops+dropped))
      & (peak'=max(peak, active))
      & (slot'=slot+1);

    // --- absorbing terminal state once the run is over ---
    [end] done -> (slot'=slot);

endmodule

label "done" = (placed=N) & (slot=HORIZON);
