# Pull requests for the Buffy repository (drafts)

The branches are pushed to `all-things-networking/buffy`. Open each PR from its compare link and paste
the text. Suggested order: `features` first (it contains `jani-backend` and the ANTLR parser from
`antlr-parser`), then `fperf-backend`.

---

## 1. `features` → `main`

Compare: https://github.com/all-things-networking/buffy/compare/main...features?expand=1

**Title:** buffyc-mc: compile Buffy to JANI and PRISM (packet classes, bounded LTL, MDP layouts)

**Body:**

Adds `buffyc-mc`, a compiler from Buffy programs to probabilistic models in JANI (Storm, Modest
`mcsta`/`modes`) and PRISM. It needs a C++17 compiler and ANTLR 4 (`make mc`). `docs/user-guide.md`
documents the language and every option; `docs/jani-backend.md` records the backend design and the
tool behaviour it relies on.

- **Front end:** an ANTLR 4 grammar (`grammar/Buffy.g4`) for the paper/URF syntax, plus a `network`
  block (instances, capacities, traffic distributions, connections, horizon, assumptions), queries and
  importance hints. `make mc` needs the ANTLR tool and C++ runtime (`brew install antlr
  antlr4-cpp-runtime`). Golden AST dumps guard the grammar (`test/parser`).
- **BuffyImmut:** one time step is symbolically executed into a hash-consed DSA expression DAG.
  Loops are unrolled, arrays flattened, queues become slots plus a length, and buffers are counts,
  per-class counts or FIFO sequences of packet classes.
- **Language additions:**
  - packet classes with `B |> pred` filters, `move-b`/`backlog-b`;
  - inferred value ranges;
  - `arrivals-p`/`drops-p`;
  - bounded-LTL queries, compiled to deterministic monitors;
  - `given` conditions, network `assume`, and `--prune-violations`.
- **JANI layouts:** `sync` (one step per time step, temporaries at assignment levels), `staged`, and
  `choose` (per-source choice edges for MDPs; the default above 64 joint choices).
- **PRISM:** temporaries as formulas, per-level stages, or merged stages (the default for large programs).

Tests: `test/jani/run_tests.sh` checks 10 small examples in every layout and mode, in Storm and `mcsta`,
against independent exact Python references (to 1e-9). The large FQ examples are compile-only;
they are validated by statistical model checking in buffy-prism.

It also removes the old AST/visitor/SMTIR skeleton, which this pipeline supersedes, and the Z3-4.8.11
build; the URF examples move to `examples/urf/`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

---

## 2. `fperf-backend` → `main` (after #1)

Compare: https://github.com/all-things-networking/buffy/compare/main...fperf-backend?expand=1

**Title:** SMT-LIB and FPerf backends for Buffy

**Body:**

Builds on `features`.

- `buffyc-mc --target smt` emits a T-step unrolled SMT-LIB model with symbolic workloads and one
  `check-sat` per query (sat ⇔ some workload realises it ⇔ Pmax > 0). Workload constraints are network
  `assume`s plus `given assumptions`.
- `include/backend/fperf/BuffyQM.hpp` turns each Buffy instance into an FPerf `QueuingModule` and the
  network into a `ContentionPoint` linked by FPerf queue edges. Its step is the instance's DSA DAG over
  FPerf's queue variables; packet identity is tracked through `move-p` events. This supersedes the
  wp/`$IN_*` substitution plan of the URF report.

Tests:
- `test/smt/run_tests.sh`: SMT answers agree with Storm on 10 programs.
- `make test-fperf`: identical SAT/UNSAT answers to FPerf's `PrioScheduler` (64 queries) and to a
  hand-written two-`PriorityQM` composition (144 queries); priority-reversed mutants disagree.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
