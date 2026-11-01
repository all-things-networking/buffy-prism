"""
Compiles a JANI model (MDP/DTMC, single automaton) to a native C step function, loaded with ctypes.

A state is a flat int32 vector (one slot per variable, plus the location if the automaton has several), so saving
and restoring a simulation anchor is an array copy, and states can be hashed and compared by value.

Supported JANI subset (anything else raises JaniUnsupported instead of being silently mistranslated):
  - one automaton (synchronisation vectors over a single automaton only rename actions), any number of locations;
  - bounded int and bool variables with constant initial values; constants with values;
  - expressions: literals, identifiers, + - * / % min max abs floor ceil, = ≠ < ≤ > ≥, ∧ ∨ ¬ ⇒, ite;
  - edges with guards, probabilistic destinations, assignments without indices (simultaneous update).
Semantics follow JANI: assignments read the old state, and an assignment outside a variable's bounds is an error.
"""
import ctypes
import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np

CACHE = Path(os.environ.get("NETMDP_JANI_CACHE", Path.home() / ".cache" / "netmdp-jani"))
CC = os.environ.get("CC", "cc")

Expr = Union[int, float, bool, str, dict]


class JaniUnsupported(Exception):
    pass


@dataclass(frozen=True)
class Variable:
    name: str
    lower: int
    upper: int
    initial: int


class _Translator:
    """ Translates JANI expressions to C, with a static int/bool/real type for each expression. """
    def __init__(self, variables: dict[str, int], constants: dict[str, Union[int, float, bool]]):
        self.variables = variables
        self.var_types: dict[str, str] = {}
        self.constants = constants

    def type_of(self, e: Expr) -> str:
        if isinstance(e, bool):
            return "bool"
        if isinstance(e, int):
            return "int"
        if isinstance(e, float):
            return "real"
        if isinstance(e, str):
            if e in self.variables:
                return self.var_types[e]
            return self.type_of(self.constants[e])
        op = e["op"]
        if op in ("=", "≠", "<", "≤", ">", "≥", "∧", "∨", "¬", "⇒"):
            return "bool"
        if op == "/":
            return "real"
        if op == "ite":
            return self.type_of(e["then"])
        if op in ("floor", "ceil"):
            return "int"
        args = [e[k] for k in ("left", "right", "exp") if k in e]
        return "real" if any(self.type_of(a) == "real" for a in args) else "int"

    def c(self, e: Expr) -> str:
        if isinstance(e, bool):
            return "1" if e else "0"
        if isinstance(e, int):
            return f"((int64_t){e})"
        if isinstance(e, float):
            return repr(e)
        if isinstance(e, str):
            if e in self.variables:
                return f"((int64_t)s[{self.variables[e]}])"
            if e in self.constants:
                return self.c(self.constants[e])
            raise JaniUnsupported(f"unknown identifier {e!r}")
        if not isinstance(e, dict) or "op" not in e:
            raise JaniUnsupported(f"unsupported expression {e!r}")
        op = e["op"]
        binary = {"+": "+", "-": "-", "*": "*", "=": "==", "≠": "!=", "<": "<", "≤": "<=", ">": ">", "≥": ">=",
                  "∧": "&&", "∨": "||"}
        if op in binary:
            return f"({self.c(e['left'])} {binary[op]} {self.c(e['right'])})"
        if op == "/":
            return f"((double){self.c(e['left'])} / (double){self.c(e['right'])})"
        if op == "%":
            return f"jm_mod({self.c(e['left'])}, {self.c(e['right'])})"
        if op in ("min", "max"):
            real = self.type_of(e) == "real"
            fn = ("fmin" if op == "min" else "fmax") if real else f"jm_i{op}"
            return f"{fn}({self.c(e['left'])}, {self.c(e['right'])})"
        if op == "¬":
            return f"(!{self.c(e['exp'])})"
        if op == "⇒":
            return f"(!{self.c(e['left'])} || {self.c(e['right'])})"
        if op == "ite":
            return f"({self.c(e['if'])} ? {self.c(e['then'])} : {self.c(e['else'])})"
        if op == "abs":
            return f"({'fabs' if self.type_of(e['exp']) == 'real' else 'llabs'}({self.c(e['exp'])}))"
        if op in ("floor", "ceil"):
            return f"((int64_t){op}((double){self.c(e['exp'])}))"
        raise JaniUnsupported(f"unsupported operator {op!r}")


_PRELUDE = r"""
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
static inline int64_t jm_imin(int64_t a, int64_t b) { return a < b ? a : b; }
static inline int64_t jm_imax(int64_t a, int64_t b) { return a > b ? a : b; }
static inline int64_t jm_mod(int64_t a, int64_t b) { int64_t r = a % b; return r < 0 ? r + (b < 0 ? -b : b) : r; }
/* xoshiro256** seeded by splitmix64, for the batch simulator */
static inline uint64_t jm_rotl(uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }
static uint64_t jm_splitmix(uint64_t *x) { uint64_t z = (*x += 0x9e3779b97f4a7c15ULL);
    z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL; z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL; return z ^ (z >> 31); }
static double jm_uniform(uint64_t s[4]) { uint64_t r = jm_rotl(s[1] * 5, 7) * 9, t = s[1] << 17;
    s[2] ^= s[0]; s[3] ^= s[1]; s[1] ^= s[2]; s[0] ^= s[3]; s[2] ^= t; s[3] = jm_rotl(s[3], 45);
    return (r >> 11) * 0x1.0p-53; }
"""


class JaniModel:
    """ A compiled JANI model. Use NativeJaniSimulator for the Simulator interface. """
    def __init__(self, jani: Union[str, Path, dict], goals: Optional[dict[str, Expr]] = None,
                 constants: Optional[dict[str, Union[int, float, bool]]] = None):
        model = json.loads(Path(jani).read_text()) if not isinstance(jani, dict) else jani
        if len(model["automata"]) != 1:
            raise JaniUnsupported("only single-automaton networks are supported")
        automaton = model["automata"][0]
        self.model_type = model["type"]
        consts = {c["name"]: c["value"] for c in model.get("constants", []) if "value" in c}
        consts.update(constants or {})
        missing = [c["name"] for c in model.get("constants", []) if c["name"] not in consts]
        if missing:
            raise JaniUnsupported(f"undefined constants {missing}")
        self.constants = consts

        raw_vars = model.get("variables", []) + automaton.get("variables", [])
        tr = _Translator({}, consts)
        self.variables: list[Variable] = []
        var_types = {}
        for v in raw_vars:
            if v.get("transient"):
                continue
            t = v["type"]
            if t == "bool":
                lo, hi, typ = 0, 1, "bool"
            elif isinstance(t, dict) and t.get("kind") == "bounded" and t.get("base") == "int":
                lo, hi, typ = int(_const_eval(t["lower-bound"], consts)), int(_const_eval(t["upper-bound"], consts)), "int"
            else:
                raise JaniUnsupported(f"variable {v['name']}: unsupported type {t!r}")
            init = int(_const_eval(v.get("initial-value", lo), consts))
            self.variables.append(Variable(v["name"], lo, hi, init))
            var_types[v["name"]] = typ
        self.locations = [loc["name"] for loc in automaton["locations"]]
        if len(self.locations) > 1:
            self.variables.append(Variable("__location", 0, len(self.locations) - 1,
                                           self.locations.index(automaton["initial-locations"][0])))
            var_types["__location"] = "int"
        self.index = {v.name: i for i, v in enumerate(self.variables)}
        tr.variables, tr.var_types = self.index, var_types
        self._tr = tr

        self.edges = automaton["edges"]
        if any(a.get("index", 0) != 0 for e in self.edges for d in e["destinations"] for a in d.get("assignments", [])):
            raise JaniUnsupported("assignment indices (sequential assignments) are not supported yet")
        # In a single-automaton network, a sync vector only renames the action.
        rename = {s["synchronise"][0]: s.get("result", s["synchronise"][0])
                  for s in model.get("system", {}).get("syncs", []) if s["synchronise"][0] is not None}
        self.edge_actions = [rename.get(e.get("action"), e.get("action")) or "τ" for e in self.edges]
        self.goals = dict(goals or {})
        self.goal_names = list(self.goals)
        source = self._generate()
        self.lib = _compile(source)
        self._bind()

    # ---- code generation -------------------------------------------------------------------------------------------
    def _generate(self) -> str:
        tr, nv, ne = self._tr, len(self.variables), len(self.edges)
        loc = self.index.get("__location")
        out = [_PRELUDE, f"#define NV {nv}", f"#define NE {ne}",
               "int jm_nvars(void) { return NV; }", "int jm_nedges(void) { return NE; }"]
        out.append("void jm_init(int32_t *s) {" + "".join(f" s[{i}] = {v.initial};" for i, v in
                                                          enumerate(self.variables)) + " }")
        out.append("int jm_enabled(const int32_t *s, int32_t *out) {\n  int k = 0;")
        for i, e in enumerate(self.edges):
            cond = tr.c(e.get("guard", {}).get("exp", True))
            if loc is not None:
                cond = f"(s[{loc}] == {self.locations.index(e['location'])}) && {cond}"
            out.append(f"  if ({cond}) out[k++] = {i};")
        out.append("  return k;\n}")
        out.append("static const int jm_nd[NE] = {" + ", ".join(str(len(e["destinations"])) for e in self.edges) + "};")
        out.append("int jm_ndest(int e) { return jm_nd[e]; }")
        out.append("double jm_prob(const int32_t *s, int e, int d) {\n  switch (e * 64 + d) {")
        for i, e in enumerate(self.edges):
            if len(e["destinations"]) > 64:
                raise JaniUnsupported("more than 64 destinations per edge")
            for j, d in enumerate(e["destinations"]):
                out.append(f"    case {i * 64 + j}: return (double)({tr.c(d.get('probability', {}).get('exp', 1))});")
        out.append("  }\n  return 0.0;\n}")
        bounds = " ".join(f"if (t[{i}] < {v.lower} || t[{i}] > {v.upper}) return -1;"
                          for i, v in enumerate(self.variables))
        out.append("int jm_apply(int32_t *s, int e, int d) {\n  int32_t t[NV]; memcpy(t, s, sizeof t);\n"
                   "  switch (e * 64 + d) {")
        for i, e in enumerate(self.edges):
            for j, d in enumerate(e["destinations"]):
                body = "".join(f" t[{self.index[a['ref']]}] = (int32_t)({tr.c(a['value'])});"
                               for a in d.get("assignments", []))
                if loc is not None:
                    body += f" t[{loc}] = {self.locations.index(d['location'])};"
                out.append(f"    case {i * 64 + j}:{body} break;")
        out.append(f"    default: return -2;\n  }}\n  {bounds}\n  memcpy(s, t, sizeof t);\n  return 0;\n}}")
        out.append("int jm_step(int32_t *s, int e, double u) {\n  int nd = jm_nd[e], d = 0;\n"
                   "  if (nd > 1) { double acc = 0.0; for (d = 0; d < nd - 1; d++) { acc += jm_prob(s, e, d);"
                   " if (u < acc) break; } }\n  int r = jm_apply(s, e, d);\n  return r < 0 ? r : d;\n}")
        out.append("int jm_goal(const int32_t *s, int g) {\n  switch (g) {")
        for g, name in enumerate(self.goal_names):
            out.append(f"    case {g}: return {tr.c(self.goals[name])};")
        out.append("  }\n  return 0;\n}")
        # Batch simulation under a memoryless scheduler given as one weight per edge (choices are drawn among the
        # enabled edges in proportion to their weights; uniformly if all enabled weights are zero).
        out.append(r"""
int64_t jm_simulate(const int32_t *s0, int64_t n_runs, int horizon, const double *edge_weight, int goal,
                    uint64_t seed, int64_t *steps_out) {
  uint64_t rng[4], x = seed; for (int i = 0; i < 4; i++) rng[i] = jm_splitmix(&x);
  int64_t hits = 0, steps = 0; int32_t s[NV], en[NE];
  for (int64_t r = 0; r < n_runs; r++) {
    memcpy(s, s0, sizeof s);
    for (int t = 0; t <= horizon; t++) {
      if (jm_goal(s, goal)) { hits++; break; }
      if (t == horizon) break;
      int k = jm_enabled(s, en); if (k == 0) break;
      int e = en[0];
      if (k > 1) {
        double tot = 0.0; for (int i = 0; i < k; i++) tot += edge_weight[en[i]];
        double u = jm_uniform(rng);
        if (tot <= 0.0) e = en[(int)(u * k)];
        else { double acc = 0.0; u *= tot; e = en[k - 1];
               for (int i = 0; i < k; i++) { acc += edge_weight[en[i]]; if (u < acc) { e = en[i]; break; } } }
      }
      if (jm_step(s, e, jm_uniform(rng)) < 0) return -1;
      steps++;
    }
  }
  if (steps_out) *steps_out = steps;
  return hits;
}

/* Like jm_simulate, but records for each run the maximum of variable score_var and how often each edge was chosen
   at decision points (states with several enabled edges); for cross-entropy / distribution learning. */
int jm_simulate_scores(const int32_t *s0, int64_t n_runs, int horizon, const double *edge_weight, int score_var,
                       uint64_t seed, int32_t *scores, int32_t *counts) {
  uint64_t rng[4], x = seed; for (int i = 0; i < 4; i++) rng[i] = jm_splitmix(&x);
  int32_t s[NV], en[NE];
  for (int64_t r = 0; r < n_runs; r++) {
    memcpy(s, s0, sizeof s);
    int32_t best = s[score_var], *cnt = counts + r * NE;
    memset(cnt, 0, NE * sizeof(int32_t));
    for (int t = 0; t < horizon; t++) {
      int k = jm_enabled(s, en); if (k == 0) break;
      int e = en[0];
      if (k > 1) {
        double tot = 0.0; for (int i = 0; i < k; i++) tot += edge_weight[en[i]];
        double u = jm_uniform(rng);
        if (tot <= 0.0) e = en[(int)(u * k)];
        else { double acc = 0.0; u *= tot; e = en[k - 1];
               for (int i = 0; i < k; i++) { acc += edge_weight[en[i]]; if (u < acc) { e = en[i]; break; } } }
        cnt[e]++;
      }
      if (jm_step(s, e, jm_uniform(rng)) < 0) return -1;
      if (s[score_var] > best) best = s[score_var];
    }
    scores[r] = best;
  }
  return 0;
}""")
        return "\n".join(out) + "\n"

    def _bind(self):
        lib, i32p, dbl = self.lib, ctypes.POINTER(ctypes.c_int32), ctypes.c_double
        lib.jm_init.argtypes = [i32p]
        lib.jm_enabled.argtypes, lib.jm_enabled.restype = [i32p, i32p], ctypes.c_int
        lib.jm_prob.argtypes, lib.jm_prob.restype = [i32p, ctypes.c_int, ctypes.c_int], dbl
        lib.jm_step.argtypes, lib.jm_step.restype = [i32p, ctypes.c_int, dbl], ctypes.c_int
        lib.jm_goal.argtypes, lib.jm_goal.restype = [i32p, ctypes.c_int], ctypes.c_int
        lib.jm_simulate.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, ctypes.POINTER(dbl), ctypes.c_int,
                                    ctypes.c_uint64, ctypes.POINTER(ctypes.c_int64)]
        lib.jm_simulate.restype = ctypes.c_int64
        lib.jm_simulate_scores.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, ctypes.POINTER(dbl), ctypes.c_int,
                                           ctypes.c_uint64, i32p, i32p]
        lib.jm_simulate_scores.restype = ctypes.c_int

    # ---- low-level API on explicit state vectors --------------------------------------------------------------------
    def initial_state(self) -> np.ndarray:
        s = np.empty(len(self.variables), dtype=np.int32)
        self.lib.jm_init(_ptr(s))
        return s

    def enabled_edges(self, s: np.ndarray) -> np.ndarray:
        out = np.empty(len(self.edges), dtype=np.int32)
        return out[:self.lib.jm_enabled(_ptr(s), _ptr(out))]

    def step(self, s: np.ndarray, edge: int, u: float) -> int:
        """ In place: takes `edge` from s, choosing the destination with the uniform number u. Returns its index. """
        d = self.lib.jm_step(_ptr(s), int(edge), float(u))
        if d < 0:
            raise RuntimeError(f"edge {edge} ({self.edge_actions[edge]}): assignment out of variable bounds")
        return d

    def goal(self, s: np.ndarray, name: str) -> bool:
        return bool(self.lib.jm_goal(_ptr(s), self.goal_names.index(name)))

    def simulate(self, n_runs: int, horizon: int, goal: str, action_weights: Optional[dict[str, float]] = None,
                 seed: int = 1, start: Optional[np.ndarray] = None) -> tuple[int, int]:
        """ Native batch runs under a memoryless action-weight scheduler; returns (goal hits, total steps). """
        w = np.array([(action_weights or {}).get(a, 0.0) for a in self.edge_actions], dtype=np.float64)
        s0 = self.initial_state() if start is None else np.ascontiguousarray(start, dtype=np.int32)
        steps = ctypes.c_int64(0)
        hits = self.lib.jm_simulate(_ptr(s0), n_runs, horizon, w.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
                                    self.goal_names.index(goal), seed, ctypes.byref(steps))
        if hits < 0:
            raise RuntimeError("assignment out of variable bounds during simulation")
        return hits, steps.value

    def simulate_scores(self, n_runs: int, horizon: int, score_var: str, edge_weights: np.ndarray,
                        seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
        """ Native batch runs under per-edge weights; returns (max of score_var per run, per-run edge choice counts). """
        w = np.ascontiguousarray(edge_weights, dtype=np.float64)
        scores = np.empty(n_runs, dtype=np.int32)
        counts = np.empty((n_runs, len(self.edges)), dtype=np.int32)
        if self.lib.jm_simulate_scores(_ptr(self.initial_state()), n_runs, horizon,
                                       w.ctypes.data_as(ctypes.POINTER(ctypes.c_double)), self.index[score_var], seed,
                                       _ptr(scores), _ptr(counts)) < 0:
            raise RuntimeError("assignment out of variable bounds during simulation")
        return scores, counts


def _ptr(a: np.ndarray):
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_int32 if a.dtype == np.int32 else ctypes.c_double))


def _const_eval(e: Expr, consts: dict) -> Union[int, float, bool]:
    if isinstance(e, (int, float, bool)):
        return e
    if isinstance(e, str):
        return _const_eval(consts[e], consts)
    ops = {"+": lambda a, b: a + b, "-": lambda a, b: a - b, "*": lambda a, b: a * b, "/": lambda a, b: a / b}
    if isinstance(e, dict) and e.get("op") in ops:
        return ops[e["op"]](_const_eval(e["left"], consts), _const_eval(e["right"], consts))
    raise JaniUnsupported(f"non-constant expression where a constant is required: {e!r}")


def _compile(source: str) -> ctypes.CDLL:
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(source.encode()).hexdigest()[:16]
    lib = CACHE / f"jani_{key}.dylib"
    if not lib.exists():
        src = CACHE / f"jani_{key}.c"
        src.write_text(source)
        tmp = lib.with_suffix(f".{os.getpid()}.tmp")
        subprocess.run([CC, "-O2", "-shared", "-fPIC", "-o", str(tmp), str(src)], check=True, capture_output=True)
        tmp.rename(lib)
    return ctypes.CDLL(str(lib))
