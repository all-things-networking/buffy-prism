"""Convert an LTL formula into an LCRL-compatible LDBA via the OWL tool.

Pipeline:  LTL string  --(owl ltl2ldba --state-acceptance)-->  HOA  -->  HoaLDBA

`HoaLDBA` subclasses ``lcrl.automata.ldba.LDBA`` and exposes exactly the API LCRL
expects of a custom LDBA (see https://github.com/grockious/lcrl#--ltl):

    * ``initial_automaton_state`` / ``automaton_state``
    * ``accepting_sets``            (generalised Büchi; a list of lists of states)
    * ``epsilon_transitions``       ({state: [epsilon-action labels]})
    * ``reset()``
    * ``step(label)``               (label = set/list of true atomic props, or an
                                     epsilon-action string; sink state is ``-1``)
    * ``accepting_frontier_function(state)``   (inherited from the base LDBA)

OWL emits a *transition-labelled, guard-nondeterministic* limit-deterministic
Büchi automaton. LCRL instead models limit-determinism with **epsilon actions**:
at a nondeterministic "guess" state the agent may take an epsilon action to jump
into an accepting component, without consuming an MDP label. We reconstruct that
representation here: a guarded jump ``q --[g]--> e`` becomes an epsilon transition
``q --epsilon--> e`` exactly when ``q`` is a genuine guess state (its edge guards
overlap) and ``e`` is *committed* (cannot reach the initial state, i.e. lies in an
accepting component). Because the accepting component itself requires ``g`` to
persist, dropping the one-symbol guard consumption is language-preserving. States
whose guards are already mutually exclusive stay fully deterministic (this covers
reachability ``F ...``, safety ``G ...`` and ``GF ...`` recurrence).
"""

import glob
import os
import subprocess

from lcrl.automata.ldba import LDBA


def find_owl(start=None):
    """Locate an OWL binary: ``$OWL_PATH``, then an ``owl-*/bin/owl`` in this
    file's ancestor directories (covers the bundled release at the repo root).
    Returns the path or ``None``."""
    env = os.environ.get("OWL_PATH")
    if env and os.path.exists(env):
        return env
    here = os.path.abspath(start or __file__)
    d = here if os.path.isdir(here) else os.path.dirname(here)
    while True:
        for hit in sorted(glob.glob(os.path.join(d, "owl-*", "bin", "owl"))):
            if os.access(hit, os.X_OK):
                return hit
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


# --------------------------------------------------------------------------- #
# OWL invocation
# --------------------------------------------------------------------------- #
def run_owl_ltl2ldba(formula: str, owl_path: str, extra_args=None) -> str:
    """Run ``owl ltl2ldba --state-acceptance`` on one formula, return HOA text."""
    args = [owl_path, "ltl2ldba", "--state-acceptance"]
    if extra_args:
        args += list(extra_args)
    args += ["-f", formula]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0 or "--BODY--" not in proc.stdout:
        raise RuntimeError(
            f"OWL failed for formula {formula!r} (exit {proc.returncode}).\n"
            f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
        )
    return proc.stdout


# --------------------------------------------------------------------------- #
# HOA parsing
# --------------------------------------------------------------------------- #
class _Hoa:
    """A parsed HOA automaton (state-based acceptance)."""

    def __init__(self):
        self.start = 0
        self.ap_names = []          # index -> proposition name
        self.num_acc_sets = 0
        self.state_marks = {}       # state -> set(acc set indices)
        self.edges = {}             # state -> list of (guard_ast, target)


def parse_hoa(hoa: str) -> _Hoa:
    aut = _Hoa()
    lines = hoa.splitlines()
    i = 0
    # ---- header ----
    while i < len(lines) and lines[i].strip() != "--BODY--":
        line = lines[i].strip()
        if line.startswith("Start:"):
            aut.start = int(line.split(":", 1)[1].strip().split()[0])
        elif line.startswith("AP:"):
            aut.ap_names = _parse_ap_line(line)
        elif line.startswith("Acceptance:"):
            aut.num_acc_sets = int(line.split(":", 1)[1].strip().split()[0])
        i += 1
    if i >= len(lines):
        raise ValueError("HOA has no --BODY--")
    i += 1  # skip --BODY--
    # ---- body ----
    cur = None
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if line == "--END--" or not line:
            continue
        if line.startswith("State:"):
            cur, marks = _parse_state_header(line)
            aut.edges.setdefault(cur, [])
            if marks:
                aut.state_marks[cur] = marks
        else:
            guard, target = _parse_edge(line)
            aut.edges[cur].append((guard, target))
    if aut.num_acc_sets == 0:
        aut.num_acc_sets = 1  # Büchi with an implicit single set
    return aut


def _parse_ap_line(line: str):
    # AP: 2 "a" "b"
    rest = line.split(":", 1)[1].strip()
    count = int(rest.split()[0])
    names = []
    j = 0
    while len(names) < count:
        j = rest.find('"', j)
        k = rest.find('"', j + 1)
        names.append(rest[j + 1:k])
        j = k + 1
    return names


def _parse_state_header(line: str):
    # State: 2 "label" {0 1}
    body = line[len("State:"):].strip()
    num = ""
    idx = 0
    while idx < len(body) and body[idx].isdigit():
        num += body[idx]
        idx += 1
    state = int(num)
    marks = set()
    if "{" in body:
        inside = body[body.index("{") + 1:body.index("}")]
        marks = {int(x) for x in inside.split()}
    return state, marks


def _parse_edge(line: str):
    # [guard] target {marks}   (marks unused under state-acceptance)
    if not line.startswith("["):
        # implicit "true" guard: "target"
        return ("t", int(line.split()[0]))
    close = line.index("]")
    guard = line[1:close].strip()
    target = int(line[close + 1:].strip().split()[0])
    return (guard, target)


# --------------------------------------------------------------------------- #
# Boolean-guard evaluation (guards are formulas over AP *indices*)
# --------------------------------------------------------------------------- #
def eval_guard(guard: str, true_indices) -> bool:
    """Evaluate a HOA guard string against the set of true AP indices."""
    pos = 0
    toks = _tokenize_guard(guard)

    def parse_or(p):
        val, p = parse_and(p)
        while p < len(toks) and toks[p] == "|":
            rhs, p = parse_and(p + 1)
            val = val or rhs
        return val, p

    def parse_and(p):
        val, p = parse_not(p)
        while p < len(toks) and toks[p] == "&":
            rhs, p = parse_not(p + 1)
            val = val and rhs
        return val, p

    def parse_not(p):
        if p < len(toks) and toks[p] == "!":
            val, p = parse_not(p + 1)
            return (not val), p
        return parse_atom(p)

    def parse_atom(p):
        t = toks[p]
        if t == "(":
            val, p = parse_or(p + 1)
            assert toks[p] == ")"
            return val, p + 1
        if t == "t":
            return True, p + 1
        if t == "f":
            return False, p + 1
        return (int(t) in true_indices), p + 1

    val, pos = parse_or(0)
    return val


def _tokenize_guard(guard: str):
    toks, num = [], ""
    for ch in guard:
        if ch.isdigit():
            num += ch
            continue
        if num:
            toks.append(num)
            num = ""
        if ch in "&|!()":
            toks.append(ch)
        elif ch in "tf":
            toks.append(ch)
        # whitespace ignored
    if num:
        toks.append(num)
    return toks


# --------------------------------------------------------------------------- #
# HOA -> LCRL LDBA
# --------------------------------------------------------------------------- #
def _reaches_start(aut: _Hoa):
    """Return the set of states from which the initial state is reachable."""
    # reverse edges
    preds = {s: set() for s in aut.edges}
    for s, es in aut.edges.items():
        for _g, t in es:
            preds.setdefault(t, set()).add(s)
    seen = {aut.start}
    stack = [aut.start]
    while stack:
        s = stack.pop()
        for p in preds.get(s, ()):
            if p not in seen:
                seen.add(p)
                stack.append(p)
    return seen


def _is_nondeterministic_state(aut: _Hoa, edges):
    """True if some AP assignment satisfies >= 2 of this state's guards."""
    idxs = sorted({i for g, _ in edges for i in _guard_indices(g)})
    if len(idxs) > 16:
        # too many to enumerate; assume deterministic backbone will be checked
        return True
    for mask in range(1 << len(idxs)):
        true_idx = {idxs[b] for b in range(len(idxs)) if mask & (1 << b)}
        hits = sum(1 for g, _ in edges if eval_guard(g, true_idx))
        if hits >= 2:
            return True
    return False


def _guard_indices(guard: str):
    return {int(t) for t in _tokenize_guard(guard) if t.isdigit()}


class HoaLDBA(LDBA):
    """An LCRL LDBA reconstructed from OWL's HOA output (see module docstring)."""

    def __init__(self, aut: _Hoa):
        self.ap_names = aut.ap_names
        can_reach_start = _reaches_start(aut)

        backbone = {}            # state -> [(guard, target)]  (label transitions)
        epsilon_transitions = {} # state -> [epsilon labels]
        eps_target = {}          # epsilon label -> target state

        for s, edges in aut.edges.items():
            nondet = len(edges) > 1 and _is_nondeterministic_state(aut, edges)
            kept = []
            for k, (g, t) in enumerate(edges):
                committed_target = t not in can_reach_start
                if nondet and committed_target and s in can_reach_start:
                    label = f"epsilon_{s}_{t}_{k}"
                    epsilon_transitions.setdefault(s, []).append(label)
                    eps_target[label] = t
                else:
                    kept.append((g, t))
            # residual nondeterminism in the label backbone is unrepresentable
            if _is_nondeterministic_state(aut, kept):
                raise NotImplementedError(
                    "OWL produced a state whose label transitions remain "
                    f"nondeterministic after epsilon extraction (state {s}). This "
                    "formula needs an LDBA shape the automatic converter does not "
                    "handle yet; encode its LDBA by hand."
                )
            backbone[s] = kept

        # state-based generalised Büchi accepting sets
        accepting_sets = []
        for acc in range(aut.num_acc_sets):
            members = sorted(s for s, m in aut.state_marks.items() if acc in m)
            accepting_sets.append(members)
        # drop empty sets but keep at least one (LCRL requires a non-None list)
        accepting_sets = [a for a in accepting_sets if a] or [[]]

        super().__init__(initial_automaton_state=aut.start, accepting_sets=accepting_sets)
        self._backbone = backbone
        self._eps_target = eps_target
        self.epsilon_transitions = epsilon_transitions

    def step(self, label):
        q = self.automaton_state
        if q == -1:
            return -1
        # epsilon action: LCRL passes the epsilon-action label (a string) directly
        if isinstance(label, str) and label in self._eps_target:
            self.automaton_state = self._eps_target[label]
            return self.automaton_state
        # normal transition on the set of true atomic propositions
        aps = {label} if isinstance(label, str) else set(label)
        true_idx = {i for i, name in enumerate(self.ap_names) if name in aps}
        for guard, target in self._backbone.get(q, ()):
            if eval_guard(guard, true_idx):
                self.automaton_state = target
                return target
        self.automaton_state = -1
        return -1


def ltl_to_ldba(formula: str, owl_path: str, extra_args=None) -> HoaLDBA:
    """Translate an (unbounded) LTL formula into an LCRL-compatible LDBA."""
    hoa = run_owl_ltl2ldba(formula, owl_path, extra_args=extra_args)
    return HoaLDBA(parse_hoa(hoa))
