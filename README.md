# buffy-prism

This repo contains my work in progress on a probabilistic verification/analysis backend for the Buffy project.

## Overview
The general idea is to define discrete-time Markov chains (DTMCs) and Markov decision processes (MDPs) that model the actions of queueing modules over streams of (possibly typed) packets. Packet arrivals (input) and dequeues (output) are represented as actions in these Markovian systems. Vectors of input buffers and control variables are the internal state. There are also rewards that can be associated with a subset of actions or predicates over states.

__Rewards are metrics that can accumulate (monotonically), whereas metrics that can reset or go up and down are better modelled as a state variable.__

__renaming modules to build contention points, add example__

See [NetAutomataSMC.pptx](/NetAutomataSMC.pptx) for some slides with examples of this construction.

## Probabilistic Model Checking with PRISM
Probabilistic model checkers can determine two basic kinds of queries, expressed as path properties in Probabilistic Computation Tree Logic (PCTL) [8, 5]:
- Probability of a path property being satisfied, which can be specified within a bounded number of time steps, an exact number of time steps, an interval of time, or (for DTMCs only) in the long run. Probability queries can test a particular probability, eg. `P<=0.98` (true/false), or solve the probability, eg. `P=?` (value in `[0,1]`), with no real difference in performance.
- Expected value of (accumulated) reward for all paths satisfying a path property. This can also take the form `R<=5.5` (true/false) or `R=?` (value in [0, inf]).

The main difference between DTMCs and MDPs: 

### DTMCs
There can be multiple transitions from a state, but each transition must be weighted, and these weights must sum to 1. I have mainly used this to model packet arrival actions (we can assume uniform likelihood for any arrival event, or define any discrete distribution). 

With DTMCs, statistical model checking is well-supported by PRISM as "Simulation" in Experiments.

### MDPs 
There can be true non-deterministic choice, in the sense of multiple transitions from a state without weights, as well as probabilistic choice as defined for DTMCs. This arguably represents a more realistic model of packet arrivals (if we don't want to commit to particular probability distributions), and the queries are then of the form `Pmax=?` and `Pmin=?` rather than `P=?`, as nondeterministic choice is expanded into branching paths (each with its own probability distribution). Simialrly for `Rmin=?` and `Rmax=?`. 

__MDPs let you avoid distribution on inputs and instead have distributions on outputs; ex. windows w/ categorical dist. for probabilistic writes.__

__Explain nondeterministic choice vs probabilistic choice, add a diagram and explain why Pmax & Pmin are often 1 and 0, which collapses the probabilistic analysis back to traditional verification.__

There has been some research on statistical model checking with MDPs that produces an counterexample scheduler in the event that the queries are unsatisfiable [6], however as far as I can tell, this is not a feature in any standard SMC tool.

__add a Punnet square for DTMC/MDP and exact/approx__

## Progress
My recent efforts have gone in several directions:

### What capabilities are gained by choosing probabilistic verification over traditional (deterministic) verification?
So far, we have estimated that statistical model checking is an effective means of rapidly locating problematic traffic conditions or out-of-spec behaviours in a large network model, that can then be solved with exact (probabilistic or deterministic) techniques. The main advantage that tools like PRISM seem to have in this regard is the ability to switch between approximate and exact methods without needing to re-encode the model.

Another area that I feel is promising is in quantifying the likelihood of constraint violations or counterexamples. It is not straightfoward with traditional verification to estimate how typical or rare a counterexample might be.

__numerical methods__

### Using probabilities to reduce state space due to orderings
I am trying to model buffers as counters for packet types, and the type of each dequeue coming from the categorical distribution associated with the current counts. This means that ordering of packets in a buffer is not modelled, which reduces the state space significantly. 

For example, with packet types `p1, p2, p3` and a buffer state `{p1: 9, p2: 6, p3: 5}`, a dequeue action could produce packet `D` where `P(D:p1)=9/20`, `P(D:p2)=6/20`, and `P(D:p3)=5/20`. Then `D:p1` means the new buffer state is `{p1: 8, p2: 6, p3: 5}`, and so on.

We also thinking about defining multiple windows (fractions of the total buffer size) to enforce partial orderings and ensure that properties like starvation are not only a result of the lack of explicit ordering in the model, but correspond to likelihood of genuine starvation in the network algorithms.

### Conditional probabilities in queries
PRISM has the basic ability to calculate conditional probabilities by dividing probabilities of multiple 
(ex. `[P=? (A & B)] / [P=? B]`, where `A` and `B` are path conditions).

This isn't as flexible as having an unconditioned Markovian process, so I am trying to model conditional probabilities as transformations of Markovian processes that prune paths violating the conditional assumption, and reweigh the remaining transitions accordingly. 

A detailed strategy is given in [2], which I believe corresponds quite directly to the "on-demand" construction algorithm I explain in [NetAutomataSMC.pptx](/NetAutomataSMC.pptx) (which I haven't really formalized yet). I estimate that my "on-demand" algorithm suffices in simple cases, but that in the general case, it will be necessary to actually use PRISM to guide the transformation (by searching paths for non-zero probabilities of violating constraints to determine when to prune), which is what [2] seems to suggest doing.

## PRISM Models

See [models/](/models/). I've included a comment block in each file that explains the general strategy and properties under test.

These are written for the [PRISM Model Checker](https://www.prismmodelchecker.org/). I have also looked into the [UPPAAL](https://uppaal.org/) and [COSMOS](https://cosmos.lacl.fr/) tools for probabilistic model checking.

## References

See also [refs-SMC.bib](/refs-SMC.bib) for BibTeX.

This is a slight overapproximation of the relevant papers to this project; I've added everything that I've come across and deemed possibly useful. In particular [2], [4], [8] and [10] have been important for my work so far.

I have included the PDF for [9] in this repo as J. Networks is defunct and I had to hunt this down on the Internet Archive.

1. G. Agha and K. Palmskog, “A Survey of Statistical Model Checking,” ACM Trans. Model. Comput. Simul., vol. 28, no. 1, p. 6:1-6:39, Jan. 2018, doi: 10.1145/3158668.
2. C. Baier, J. Klein, S. Klüppelholz, and S. Märcker, “Computing Conditional Probabilities in Markovian Models Efficiently,” in Tools and Algorithms for the Construction and Analysis of Systems, E. Ábrahám and K. Havelund, Eds., Berlin, Heidelberg: Springer, 2014, pp. 515–530. doi: 10.1007/978-3-642-54862-8_43.
3. M. E. Andrés and P. van Rossum, “Conditional Probabilities over Probabilistic and Nondeterministic Systems,” in Tools and Algorithms for the Construction and Analysis of Systems, C. R. Ramakrishnan and J. Rehof, Eds., Berlin, Heidelberg: Springer, 2008, pp. 157–172. doi: 10.1007/978-3-540-78800-3_12.
4. C. Baier, M. Größer, and F. Ciesinski, “Model Checking Linear-Time Properties of Probabilistic Systems,” in Handbook of Weighted Automata, M. Droste, W. Kuich, and H. Vogler, Eds., Berlin, Heidelberg: Springer, 2009, pp. 519–570. doi: 10.1007/978-3-642-01492-5_13.
5. M. Kwiatkowska, G. Norman, and D. Parker, “PRISM 4.0: Verification of Probabilistic Real-time Systems,” in Proc. 23rd International Conference on Computer Aided Verification (CAV’11), G. Gopalakrishnan and S. Qadeer, Eds., in LNCS, vol. 6806. Springer, 2011, pp. 585–591.
6. M. Y. Vardi, “Probabilistic Linear-Time Model Checking: An Overview of the Automata-Theoretic Approach,” in Proceedings of the 5th International AMAST Workshop on Formal Methods for Real-Time and Probabilistic Systems, in ARTS ’99. Berlin, Heidelberg: Springer-Verlag, May 1999, pp. 265–276.
7. D. Henriques, J. G. Martins, P. Zuliani, A. Platzer, and E. M. Clarke, “Statistical Model Checking for Markov Decision Processes,” in 2012 Ninth International Conference on Quantitative Evaluation of Systems, Sep. 2012, pp. 84–93. doi: 10.1109/QEST.2012.19.
8. M. Kwiatkowska, G. Norman, and D. Parker, “Stochastic Model Checking,” in Formal Methods for the Design of Computer, Communication and Software Systems: Performance Evaluation (SFM’07), M. Bernardo and J. Hillston, Eds., in LNCS (Tutorial Volume), vol. 4486. Springer, 2007, pp. 220–270.
9. M. Ji, D. Wu, and Z. Chen, “Verification Method of Conditional Probability Based on Automaton,” J. Networks, vol. 8, no. 6, pp. 1329–1335, 2013, doi: 10.4304/JNW.8.6.1329-1335.
10. M. Mohri, “Weighted Automata Algorithms,” in Handbook of Weighted Automata, M. Droste, W. Kuich, and H. Vogler, Eds., Berlin, Heidelberg: Springer, 2009, pp. 213–254. doi: 10.1007/978-3-642-01492-5_6.
