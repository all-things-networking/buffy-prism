// Priority queue scheduler
// 4 inputs (1,2,3,4) and 1 output (O)
// Buffers have variable length b; states are current backlog size
// Packet types Σ = {N,1,2} 
// 0-1 packets arrive at each time step (N = “no packet arrived”)

// Constraints:
// None

dtmc

const int T;
// const int T = 100;
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
formula read     = (rw=0);
formula arrival  = (rw=1);
formula write    = (rw=2);
formula a0000 = (rw=1)&(a1=0)&(a2=0)&(a3=0)&(a4=0);
formula a0001 = (rw=1)&(a1=0)&(a2=0)&(a3=0)&(a4=1);
formula a0010 = (rw=1)&(a1=0)&(a2=0)&(a3=1)&(a4=0);
formula a0100 = (rw=1)&(a1=0)&(a2=1)&(a3=0)&(a4=0);
formula a1000 = (rw=1)&(a1=1)&(a2=0)&(a3=0)&(a4=0);
formula a0011 = (rw=1)&(a1=0)&(a2=0)&(a3=1)&(a4=1);
formula a0101 = (rw=1)&(a1=0)&(a2=1)&(a3=0)&(a4=1);
formula a1001 = (rw=1)&(a1=1)&(a2=0)&(a3=0)&(a4=1);
formula a0110 = (rw=1)&(a1=0)&(a2=1)&(a3=1)&(a4=0);
formula a1010 = (rw=1)&(a1=1)&(a2=0)&(a3=1)&(a4=0);
formula a1100 = (rw=1)&(a1=1)&(a2=1)&(a3=0)&(a4=0);
formula a0111 = (rw=1)&(a1=0)&(a2=1)&(a3=1)&(a4=1);
formula a1101 = (rw=1)&(a1=1)&(a2=1)&(a3=0)&(a4=1);
formula a1011 = (rw=1)&(a1=1)&(a2=0)&(a3=1)&(a4=1);
formula a1110 = (rw=1)&(a1=1)&(a2=1)&(a3=1)&(a4=0);
formula a1111 = (rw=1)&(a1=1)&(a2=1)&(a3=1)&(a4=1);

module pq4

	b1: [0..b] init 0; // buff 1 current backlog # of packets
	b2: [0..b] init 0; // buff 2 current backlog # of packets
	b3: [0..b] init 0; // buff 3 current backlog # of packets
	b4: [0..b] init 0; // buff 4 current backlog # of packets
	a1: [0..1] init 0; // buff 1 # of arrivals
	a2: [0..1] init 0; // buff 2 # of arrivals
	a3: [0..1] init 0; // buff 3 # of arrivals
	a4: [0..1] init 0; // buff 4 # of arrivals
	rw: [0..2] init 0; // 0=read, 1=arrival, 2=write

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

	// write states
	[w0] write & empty1 & empty2 & empty3 & empty4 -> 
		(rw'=0) & (a1'=0) & (a2'=0) & (a3'=0) & (a4'=0);

	[w1] write & !empty1 -> 
		(b1'=b1-1) & (blocked_1'=0) & (rw'=0) &
		// (blocked_2'=!empty2 ? blocked_2+1 : 0) & 
		// (blocked_3'=!empty3 ? blocked_3+1 : 0) & 
		// (blocked_4'=!empty4 ? blocked_4+1 : 0);
		(blocked_2'=(!empty2 & blocked_2<T) ? blocked_2+1 : 0) & 
		(blocked_3'=(!empty3 & blocked_3<T) ? blocked_3+1 : 0) & 
		(blocked_4'=(!empty4 & blocked_4<T) ? blocked_4+1 : 0);

	[w2] write & empty1 & !empty2 -> 
		(b2'=b2-1) & (blocked_2'=0) & (rw'=0) &
		// (blocked_3'=!empty3 ? blocked_3+1 : 0) & 
		// (blocked_4'=!empty4 ? blocked_4+1 : 0);
		(blocked_3'=(!empty3 & blocked_3<T) ? blocked_3+1 : 0) & 
		(blocked_4'=(!empty4 & blocked_4<T) ? blocked_4+1 : 0);
					  
	[w3] write & empty1 & empty2 & !empty3 -> 
		(b3'=b3-1) & (blocked_3'=0) & (rw'=0) &
		// (blocked_4'=!empty4 ? blocked_4+1 : 0);
		(blocked_4'=(!empty4 & blocked_4<T) ? blocked_4+1 : 0);

	[w4] write & empty1 & empty2 & empty3 & !empty4 -> 
		(b4'=b4-1) & (blocked_4'=0) & (rw'=0);

	
	// read - transition to any arrival state with equal probability
	[rstep] read -> 0.0625:(rw'=1)&(a1'=0)&(a2'=0)&(a3'=0)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=0)&(a3'=0)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=0)&(a3'=1)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=1)&(a3'=0)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=0)&(a3'=0)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=0)&(a3'=1)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=1)&(a3'=0)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=0)&(a3'=0)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=1)&(a3'=1)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=0)&(a3'=1)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=1)&(a3'=0)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=0)&(a2'=1)&(a3'=1)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=0)&(a3'=1)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=1)&(a3'=0)&(a4'=1) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=1)&(a3'=1)&(a4'=0) +
			0.0625:(rw'=1)&(a1'=1)&(a2'=1)&(a3'=1)&(a4'=1);

	// arrival states - update buffer capacities as appropriate
	[] a0000 -> (rw'=2);
	[] a0001 -> (b4'=(full4 ? b4 : b4+1)) & (rw'=2) & (a4'=0);
	[] a0010 -> (b3'=(full3 ? b3 : b3+1)) & (rw'=2) & (a3'=0);
	[] a0100 -> (b2'=(full2 ? b2 : b2+1)) & (rw'=2) & (a2'=0);
	[] a1000 -> (b1'=(full1 ? b1 : b1+1)) & (rw'=2) & (a1'=0);
	[] a1100 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b2'=(full2 ? b2 : b2+1)) & 
		    (rw'=2) & (a1'=0) & (a2'=0);
	[] a1010 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b3'=(full3 ? b3 : b3+1)) & 
		    (rw'=2) & (a1'=0) & (a3'=0);
	[] a1001 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a1'=0) & (a4'=0);
	[] a0110 -> (b2'=(full2 ? b2 : b2+1)) & 
		    (b3'=(full3 ? b3 : b3+1)) & 
		    (rw'=2) & (a2'=0) & (a3'=0);
	[] a0101 -> (b2'=(full2 ? b2 : b2+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a2'=0) & (a4'=0);
	[] a0011 -> (b3'=(full3 ? b3 : b3+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a3'=0) & (a4'=0);
	[] a0111 -> (b2'=(full2 ? b2 : b2+1)) & 
		    (b3'=(full3 ? b3 : b3+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a2'=0) & (a3'=0) & (a4'=0);
	[] a1011 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b3'=(full3 ? b3 : b3+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a1'=0) & (a3'=0) & (a4'=0);
	[] a1101 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b2'=(full2 ? b2 : b2+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a1'=0) & (a2'=0) & (a4'=0);
	[] a1110 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b2'=(full2 ? b2 : b2+1)) & 
		    (b3'=(full3 ? b3 : b3+1)) & 
		    (rw'=2) & (a1'=0) & (a2'=0) & (a3'=0);
	[] a1111 -> (b1'=(full1 ? b1 : b1+1)) & 
		    (b2'=(full2 ? b2 : b2+1)) & 
		    (b3'=(full3 ? b3 : b3+1)) & 
		    (b4'=(full4 ? b4 : b4+1)) & 
		    (rw'=2) & (a1'=0) & (a2'=0) & (a3'=0) & (a4'=0);
endmodule

//rewards

rewards "time_steps"
    [rstep] true : 1;
endrewards
rewards "cenq_1"
    a1=1 : 1;
endrewards
rewards "cenq_2"
    a2=1 : 1;
endrewards
rewards "cenq_3"
    a3=1 : 1;
endrewards
rewards "cenq_4"
    a4=1 : 1;
endrewards

// labels

// a philosopher is hungry
// label "hungry" = ((p1>0)&(p1<8))|((p2>0)&(p2<8))|((p3>0)&(p3<8)); 