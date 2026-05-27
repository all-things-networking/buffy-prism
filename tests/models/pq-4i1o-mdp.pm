// Priority queue scheduler
// 4 inputs (1,2,3,4) and 1 output (O)
// Buffers have variable length b; states are current backlog size
// Packet types Σ = {N,1,2} 
// 0-1 packets arrive at each time step (N = “no packet arrived”)

// Constraints:
// None

mdp

const int T = 100;
const int b = 8;

// formulae
formula empty1 = (b1=0);
formula empty2 = (b2=0);
formula empty3 = (b3=0);
formula empty4 = (b4=0);
formula full1  = (b1=b);
formula full2  = (b2=b);
formula full3  = (b3=b);
formula full4  = (b4=b);
formula read   = (rw=0);
formula write  = (rw=1);

module pq4

	b1: [0..b] init 0; // buff 1 # of packets
	b2: [0..b] init 0; // buff 2 # of packets
	b3: [0..b] init 0; // buff 3 # of packets
	b4: [0..b] init 0; // buff 4 # of packets
	rw: [0..1] init 0; // 0=read, 1=write

	// unbounded blocked counters -- for statistical model checking
	// blocked_1 : int init 0;
	// blocked_2 : int init 0;
	// blocked_3 : int init 0;
	// blocked_4 : int init 0;

	// bounded blocked counters -- cannot exceed T
	blocked_1 : [0..T] init 0;
	blocked_2 : [0..T] init 0;
	blocked_3 : [0..T] init 0;
	blocked_4 : [0..T] init 0;

	[w0] write & empty1 & empty2 & empty3 & empty4 -> (rw'=0);

	[w1] write & !empty1 -> (b1'=b1-1) & (blocked_1'=0) & (blocked_2'= (!empty2 & blocked_2<T) ? blocked_2+1 : 0) & (blocked_3'= (!empty3 & blocked_3<T) ? blocked_3+1 : 0) & (blocked_4'= (!empty4 & blocked_4<T) ? blocked_4+1 : 0) & (rw'=0);
	[w2] write &  empty1 & !empty2 -> (b2'=b2-1) & (blocked_2'=0) & (blocked_3'= (!empty3 & blocked_3<T) ? blocked_3+1 : 0) & (blocked_4'= (!empty4 & blocked_4<T) ? blocked_4+1 : 0) & (rw'=0);
	[w3] write &  empty1 &  empty2 & !empty3 -> (b3'=b3-1) & (blocked_3'=0) & (blocked_4'= (!empty4 & blocked_4<T) ? blocked_4+1 : 0) & (rw'=0);
	[w4] write &  empty1 &  empty2 &  empty3 & !empty4 -> (b4'=b4-1) & (blocked_4'=0) & (rw'=0);

	// UNNECCESSARY [a0000] true -> true;

	// a0001
	[a0001] read & !full4 -> (b4'=b4+1) & (rw'=1);
	[a0001] read &  full4 -> (rw'=1);

	// a0010
	[a0010] read & !full3 -> (b3'=b3+1) & (rw'=1);
	[a0010] read &  full3 -> (rw'=1);

	// a0100
	[a0100] read & !full2 -> (b2'=b2+1) & (rw'=1);
	[a0100] read &  full2 -> (rw'=1);

	// a1000
	[a1000] read & !full1 -> (b1'=b1+1) & (rw'=1);
	[a1000] read &  full1 -> (rw'=1);

	// a1100
	[a1100] read & !full1 & !full2 -> (b1'=b1+1) & (b2'=b2+1) & (rw'=1);
	[a1100] read & !full1 &  full2 -> (b1'=b1+1) & (rw'=1);
	[a1100] read &  full1 & !full2 -> (b2'=b2+1) & (rw'=1);
	[a1100] read &  full1 &  full2 -> (rw'=1);

	// a1010
	[a1010] read & !full1 & !full3 -> (b1'=b1+1) & (b3'=b3+1) & (rw'=1);
	[a1010] read & !full1 &  full3 -> (b1'=b1+1) & (rw'=1);
	[a1010] read &  full1 & !full3 -> (b3'=b3+1) & (rw'=1);
	[a1010] read &  full1 &  full3 -> (rw'=1);

	// a1001
	[a1001] read & !full1 & !full4 -> (b1'=b1+1) & (b4'=b4+1) & (rw'=1);
	[a1001] read & !full1 &  full4 -> (b1'=b1+1) & (rw'=1);
	[a1001] read &  full1 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a1001] read &  full1 &  full4 -> (rw'=1);

	// a0110
	[a0110] read & !full2 & !full3 -> (b2'=b2+1) & (b3'=b3+1) & (rw'=1);
	[a0110] read & !full2 &  full3 -> (b2'=b2+1) & (rw'=1);
	[a0110] read &  full2 & !full3 -> (b3'=b3+1) & (rw'=1);
	[a0110] read &  full2 &  full3 -> (rw'=1);

	// a0101
	[a0101] read & !full2 & !full4 -> (b2'=b2+1) & (b4'=b4+1) & (rw'=1);
	[a0101] read & !full2 &  full4 -> (b2'=b2+1) & (rw'=1);
	[a0101] read &  full2 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a0101] read &  full2 &  full4 -> (rw'=1);

	// a0011
	[a0011] read & !full3 & !full4 -> (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a0011] read & !full3 &  full4 -> (b3'=b3+1) & (rw'=1);
	[a0011] read &  full3 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a0011] read &  full3 &  full4 -> (rw'=1);

	// a0111
	[a0111] read & !full2 & !full3 & !full4 -> (b2'=b2+1) & (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a0111] read & !full2 & !full3 &  full4 -> (b2'=b2+1) & (b3'=b3+1) & (rw'=1);
	[a0111] read & !full2 &  full3 & !full4 -> (b2'=b2+1) & (b4'=b4+1) & (rw'=1);
	[a0111] read & !full2 &  full3 &  full4 -> (b2'=b2+1) & (rw'=1);

	[a0111] read &  full2 & !full3 & !full4 -> (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a0111] read &  full2 & !full3 &  full4 -> (b3'=b3+1) & (rw'=1);
	[a0111] read &  full2 &  full3 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a0111] read &  full2 &  full3 &  full4 -> (rw'=1);

	// a1011
	[a1011] read & !full1 & !full3 & !full4 -> (b1'=b1+1) & (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a1011] read & !full1 & !full3 &  full4 -> (b1'=b1+1) & (b3'=b3+1) & (rw'=1);
	[a1011] read & !full1 &  full3 & !full4 -> (b1'=b1+1) & (b4'=b4+1) & (rw'=1);
	[a1011] read & !full1 &  full3 &  full4 -> (b1'=b1+1) & (rw'=1);

	[a1011] read &  full1 & !full3 & !full4 -> (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a1011] read &  full1 & !full3 &  full4 -> (b3'=b3+1) & (rw'=1);
	[a1011] read &  full1 &  full3 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a1011] read &  full1 &  full3 &  full4 -> (rw'=1);

	// a1101
	[a1101] read & !full1 & !full2 & !full4 -> (b1'=b1+1) & (b2'=b2+1) & (b4'=b4+1) & (rw'=1);
	[a1101] read & !full1 & !full2 &  full4 -> (b1'=b1+1) & (b2'=b2+1) & (rw'=1);
	[a1101] read & !full1 &  full2 & !full4 -> (b1'=b1+1) & (b4'=b4+1) & (rw'=1);
	[a1101] read & !full1 &  full2 &  full4 -> (b1'=b1+1) & (rw'=1);

	[a1101] read &  full1 & !full2 & !full4 -> (b2'=b2+1) & (b4'=b4+1) & (rw'=1);
	[a1101] read &  full1 & !full2 &  full4 -> (b2'=b2+1) & (rw'=1);
	[a1101] read &  full1 &  full2 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a1101] read &  full1 &  full2 &  full4 -> (rw'=1);

	// a1110
	[a1110] read & !full1 & !full2 & !full3 -> (b1'=b1+1) & (b2'=b2+1) & (b3'=b3+1) & (rw'=1);
	[a1110] read & !full1 & !full2 &  full3 -> (b1'=b1+1) & (b2'=b2+1) & (rw'=1);
	[a1110] read & !full1 &  full2 & !full3 -> (b1'=b1+1) & (b3'=b3+1) & (rw'=1);
	[a1110] read & !full1 &  full2 &  full3 -> (b1'=b1+1) & (rw'=1);

	[a1110] read &  full1 & !full2 & !full3 -> (b2'=b2+1) & (b3'=b3+1) & (rw'=1);
	[a1110] read &  full1 & !full2 &  full3 -> (b2'=b2+1) & (rw'=1);
	[a1110] read &  full1 &  full2 & !full3 -> (b3'=b3+1) & (rw'=1);
	[a1110] read &  full1 &  full2 &  full3 -> (rw'=1);

	// a1111
	[a1111] read & !full1 & !full2 & !full3 & !full4 -> (b1'=b1+1) & (b2'=b2+1) & (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read & !full1 & !full2 & !full3 &  full4 -> (b1'=b1+1) & (b2'=b2+1) & (b3'=b3+1) & (rw'=1);
	[a1111] read & !full1 & !full2 &  full3 & !full4 -> (b1'=b1+1) & (b2'=b2+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read & !full1 & !full2 &  full3 &  full4 -> (b1'=b1+1) & (b2'=b2+1) & (rw'=1);

	[a1111] read & !full1 &  full2 & !full3 & !full4 -> (b1'=b1+1) & (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read & !full1 &  full2 & !full3 &  full4 -> (b1'=b1+1) & (b3'=b3+1) & (rw'=1);
	[a1111] read & !full1 &  full2 &  full3 & !full4 -> (b1'=b1+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read & !full1 &  full2 &  full3 &  full4 -> (b1'=b1+1) & (rw'=1);

	[a1111] read &  full1 & !full2 & !full3 & !full4 -> (b2'=b2+1) & (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read &  full1 & !full2 & !full3 &  full4 -> (b2'=b2+1) & (b3'=b3+1) & (rw'=1);
	[a1111] read &  full1 & !full2 &  full3 & !full4 -> (b2'=b2+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read &  full1 & !full2 &  full3 &  full4 -> (b2'=b2+1) & (rw'=1);

	[a1111] read &  full1 &  full2 & !full3 & !full4 -> (b3'=b3+1) & (b4'=b4+1) & (rw'=1);
	[a1111] read &  full1 &  full2 & !full3 &  full4 -> (b3'=b3+1) & (rw'=1);
	[a1111] read &  full1 &  full2 &  full3 & !full4 -> (b4'=b4+1) & (rw'=1);
	[a1111] read &  full1 &  full2 &  full3 &  full4 -> (rw'=1);
endmodule

//rewards

rewards "cenq_1"
    [a1000] !full1 : 1;
    [a1001] !full1 : 1;
    [a1010] !full1 : 1;
    [a1011] !full1 : 1;
    [a1100] !full1 : 1;
    [a1101] !full1 : 1;
    [a1110] !full1 : 1;
    [a1111] !full1 : 1;
endrewards
rewards "cenq_2"
    [a0100] !full2 : 1;
    [a0101] !full2 : 1;
    [a0110] !full2 : 1;
    [a0111] !full2 : 1;
    [a1100] !full2 : 1;
    [a1101] !full2 : 1;
    [a1110] !full2 : 1;
    [a1111] !full2 : 1;
endrewards
rewards "cenq_3"
    [a0010] !full3 : 1;
    [a0011] !full3 : 1;
    [a0110] !full3 : 1;
    [a0111] !full3 : 1;
    [a1010] !full3 : 1;
    [a1011] !full3 : 1;
    [a1110] !full3 : 1;
    [a1111] !full3 : 1;
endrewards
rewards "cenq_4"
    [a0001] !full4 : 1;
    [a0011] !full4 : 1;
    [a0101] !full4 : 1;
    [a0111] !full4 : 1;
    [a1001] !full4 : 1;
    [a1011] !full4 : 1;
    [a1101] !full4 : 1;
    [a1111] !full4 : 1;
endrewards

// labels

// a philosopher is hungry
// label "hungry" = ((p1>0)&(p1<8))|((p2>0)&(p2<8))|((p3>0)&(p3<8)); 