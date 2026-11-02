"""
Compiles a JANI model (MDP/DTMC, single automaton) to a native C step function, loaded with ctypes.

A state is a flat int32 vector (one slot per variable, plus the location if the automaton has several), so saving
and restoring a simulation anchor is an array copy, and states can be hashed and compared by value.

Supported JANI subset (anything else raises JaniUnsupported instead of being silently mistranslated):
  - networks of automata composed by synchronisation vectors (silent edges interleave), any number of locations;
  - bounded int and bool variables with constant initial values; constants with values;
  - expressions: literals, identifiers, + - * / % min max abs floor ceil, = ≠ < ≤ > ≥, ∧ ∨ ¬ ⇒, ite;
  - edges with guards, probabilistic destinations, assignments with optional indices (ordered levels);
  - transient variables (bool/int): reset every step, readable at later assignment levels, initial value elsewhere;
    real transients are transition rewards (write-only), summed by simulate_rewards.
Semantics follow JANI: assignment levels run in index order, each level updating simultaneously from the state left
by the previous levels; an assignment outside a variable's bounds is an error.
"""
import ctypes
import hashlib
import itertools
import json
import os
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import Callable, Optional, Sequence, Union

import numpy as np

CACHE = Path(os.environ.get("NETMDP_JANI_CACHE", Path.home() / ".cache" / "netmdp-jani"))
CC = os.environ.get("CC", "cc")

Expr = Union[int, float, bool, str, dict]
# Schedulers accepted by the batch simulators: per-action weights (memoryless; None = uniform) or a NativePolicy.
Scheduling = Union[None, dict[str, float], "NativePolicy"]


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
/* policy tables: open addressing on a hash of the key values (slot = row index, -1 = empty) */
static uint64_t jm_khash(const int32_t *v, int n) { uint64_t h = 0xcbf29ce484222325ULL;
    for (int i = 0; i < n; i++) { h ^= (uint32_t)v[i]; h *= 0x100000001b3ULL; h ^= h >> 29; } return h; }
int jm_table_fill(int64_t nrows, int nkey, const int32_t *keys, int64_t mask, int32_t *slot) {
  for (int64_t h = 0; h <= mask; h++) slot[h] = -1;
  for (int64_t r = 0; r < nrows; r++) {
    const int32_t *k = keys + r * nkey; uint64_t h = jm_khash(k, nkey) & mask;
    for (; slot[h] >= 0; h = (h + 1) & mask)
      if (!memcmp(keys + (int64_t)slot[h] * nkey, k, nkey * sizeof(int32_t))) return -5;
    slot[h] = (int32_t)r;
  }
  return 0;
}
"""


# Schedulers for the batch simulators. A policy maps (state, step count t, enabled edges) to weights over the enabled
# edges; the choice is drawn in proportion to them. Sources, in order: a callback (any function of state and t), else
# a table row looked up by the key (s[keyvar[0]], ..., with keyvar = -1 standing for t), holding (edge, weight) pairs;
# if neither applies or the weights of the enabled edges sum to 0, the default per-edge weights w; uniform if those sum
# to 0 too. Policies depend on (state, t) only, which the splitting trajectories carry, so splitting stays unbiased.
_POLICY = r"""
typedef int (*jm_policy_cb)(const int32_t *s, int t, const int32_t *en, int k, double *w);
typedef struct {
  const double *w;                         /* NE default per-edge weights */
  int64_t mask;                            /* table slots - 1 (a power of two minus 1); -1: no table */
  const int32_t *slot, *keyvar, *keys;     /* slot -> row; key variables; nrows * nkey key values */
  int32_t nkey;
  const int64_t *row_off;                  /* row r holds pairs row_off[r] .. row_off[r+1]-1 */
  const int32_t *row_edge; const double *row_w;
  jm_policy_cb cb;
} jm_policy;

/* Draws one of the k > 1 enabled edges en[0..k-1] in state s at step t; returns it, or -4 if the callback failed. */
static int jm_pick(const jm_policy *p, const int32_t *s, int t, const int32_t *en, int k, uint64_t rng[4]) {
  double wk[NE], tot = 0.0; int have = 0;
  if (p->cb) {
    if (p->cb(s, t, en, k, wk)) return -4;
    have = 1;
  } else if (p->mask >= 0) {
    int32_t key[NV + 1];
    for (int j = 0; j < p->nkey; j++) key[j] = p->keyvar[j] < 0 ? t : s[p->keyvar[j]];
    for (uint64_t h = jm_khash(key, p->nkey) & p->mask; p->slot[h] >= 0; h = (h + 1) & p->mask) {
      int64_t r = p->slot[h];
      if (memcmp(p->keys + r * p->nkey, key, p->nkey * sizeof(int32_t))) continue;
      for (int i = 0; i < k; i++) {
        wk[i] = 0.0;
        for (int64_t j = p->row_off[r]; j < p->row_off[r + 1]; j++) if (p->row_edge[j] == en[i]) wk[i] = p->row_w[j];
      }
      have = 1; break;
    }
  }
  if (have) for (int i = 0; i < k; i++) tot += wk[i];
  if (tot <= 0.0) { tot = 0.0; for (int i = 0; i < k; i++) tot += (wk[i] = p->w[en[i]]); }
  double u = jm_uniform(rng);
  if (tot <= 0.0) return en[(int)(u * k)];
  double acc = 0.0; u *= tot;
  for (int i = 0; i < k; i++) { acc += wk[i]; if (u < acc) return en[i]; }
  return en[k - 1];
}
"""


# Native importance splitting. Levels: thresholds thr[0] < ... < thr[nlev-1] on an importance function;
# level(s) = number of thresholds <= imp(s). Choices are resolved by a jm_policy, as in jm_simulate.
_SPLITTING = r"""
static int jm_level(int64_t v, int nlev, const int64_t *thr) { int l = 0; while (l < nlev && v >= thr[l]) l++; return l; }
/* the edge taken from s at step t: -1 on a deadlock, -4 if the policy callback failed */
static int jm_choose(const int32_t *s, int t, const jm_policy *pol, uint64_t rng[4], int32_t *en) {
  int k = jm_enabled(s, en); if (k == 0) return -1; if (k == 1) return en[0];
  return jm_pick(pol, s, t, en, k, rng);
}
typedef struct { int32_t s[NV]; int32_t t; int32_t clev; } jm_traj;

/* RESTART (Villen-Altamirano): a trajectory that up-crosses threshold i (from below) splits into fac[i] copies
   (itself + fac[i]-1 retrials created at level i+1); a retrial created at level c > 0 is killed when its level
   drops below c. Re-crossings split again. A goal hit at level l adds 1/prod_{i<l} fac[i]. Per-run estimates go to
   out[r] (unbiased for P(goal within horizon)). Returns 0, or -1 (bounds error) / -2 (more than max_traj) /
   -4 (policy callback failed). */
int jm_restart(const int32_t *s0, int64_t n_runs, int horizon, const jm_policy *pol, int goal, int imp, int nlev,
               const int64_t *thr, const int32_t *fac, uint64_t seed, int64_t max_traj, double *out, int64_t *steps_out) {
  uint64_t rng[4], x = seed; for (int i = 0; i < 4; i++) rng[i] = jm_splitmix(&x);
  double wl[65]; wl[0] = 1.0; for (int i = 0; i < nlev && i < 64; i++) wl[i + 1] = wl[i] / fac[i];
  if (nlev > 64) return -3;
  int64_t cap = 1024, steps = 0; jm_traj *stk = malloc(cap * sizeof(jm_traj)); int32_t en[NE];
  if (!stk) return -2;
  for (int64_t r = 0; r < n_runs; r++) {
    int64_t top = 0; double est = 0.0;
    memcpy(stk[0].s, s0, sizeof stk[0].s); stk[0].t = 0; stk[0].clev = 0; top = 1;
    while (top > 0) {
      jm_traj cur = stk[--top];
      int lvl = jm_level(jm_imp(cur.s, imp), nlev, thr);
      for (;;) {
        if (jm_goal(cur.s, goal)) { est += wl[lvl]; break; }
        if (cur.t >= horizon) break;
        int e = jm_choose(cur.s, cur.t, pol, rng, en);
        if (e == -4) { free(stk); return -4; }
        if (e < 0) break;
        if (jm_step(cur.s, e, jm_uniform(rng)) < 0) { free(stk); return -1; }
        cur.t++; steps++;
        int nl = jm_level(jm_imp(cur.s, imp), nlev, thr);
        if (nl < cur.clev) break;                      /* retrial fell below its creation level */
        if (nl > lvl) {                                /* split once per crossed threshold */
          int64_t group = 1;
          for (int i = lvl; i < nl; i++) {
            int64_t add = group * (fac[i] - 1);
            if (top + add > max_traj) { free(stk); return -2; }
            while (top + add > cap) { cap *= 2; jm_traj *g = realloc(stk, cap * sizeof(jm_traj));
                                      if (!g) { free(stk); return -2; } stk = g; }
            for (int64_t j = 0; j < add; j++) { stk[top] = cur; stk[top].clev = i + 1; top++; }
            group *= fac[i];
          }
        }
        lvl = nl;
      }
    }
    out[r] = est;
  }
  free(stk);
  if (steps_out) *steps_out = steps;
  return 0;
}

/* Fixed effort: at level i, eff[i] trials, each from an entrance state of level i drawn uniformly with replacement
   (entrance states kept with multiplicity); a trial succeeds on reaching level i+1 (or the goal, at the last level)
   before the horizon. Estimate prod_i succ_i / eff[i]. Per-level success counts go to succ[r*(nlev+1)+i] if succ is
   not NULL (used by the expected-success level selection). */
int jm_fixed_effort(const int32_t *s0, int64_t n_runs, int horizon, const jm_policy *pol, int goal, int imp, int nlev,
                    const int64_t *thr, const int32_t *eff, uint64_t seed, double *out, int32_t *succ,
                    int64_t *steps_out) {
  uint64_t rng[4], x = seed; for (int i = 0; i < 4; i++) rng[i] = jm_splitmix(&x);
  int32_t maxeff = 1; for (int i = 0; i <= nlev; i++) if (eff[i] > maxeff) maxeff = eff[i];
  jm_traj *cur = malloc((size_t)maxeff * sizeof(jm_traj)), *nxt = malloc((size_t)maxeff * sizeof(jm_traj));
  int32_t en[NE]; int64_t steps = 0;
  if (!cur || !nxt) { free(cur); free(nxt); return -2; }
  for (int64_t r = 0; r < n_runs; r++) {
    int ncur = 1; memcpy(cur[0].s, s0, sizeof cur[0].s); cur[0].t = 0;
    double est = 1.0;
    for (int i = 0; i <= nlev; i++) {
      int ok = 0, nn = 0;
      for (int j = 0; j < eff[i]; j++) {
        jm_traj tr = cur[(int)(jm_uniform(rng) * ncur)];
        int hit = 0;
        for (;;) {
          if (jm_goal(tr.s, goal)) { hit = 1; break; }
          if (i < nlev && jm_level(jm_imp(tr.s, imp), nlev, thr) > i) { hit = 1; break; }
          if (tr.t >= horizon) break;
          int e = jm_choose(tr.s, tr.t, pol, rng, en);
          if (e == -4) { free(cur); free(nxt); return -4; }
          if (e < 0) break;
          if (jm_step(tr.s, e, jm_uniform(rng)) < 0) { free(cur); free(nxt); return -1; }
          tr.t++; steps++;
        }
        if (hit) { ok++; if (i < nlev) nxt[nn++] = tr; }
      }
      if (succ) succ[r * (nlev + 1) + i] = ok;
      est *= (double)ok / eff[i];
      if (ok == 0) { if (succ) for (int k = i + 1; k <= nlev; k++) succ[r * (nlev + 1) + k] = 0; break; }
      jm_traj *tmp = cur; cur = nxt; nxt = tmp; ncur = nn;
    }
    out[r] = est;
  }
  free(cur); free(nxt);
  if (steps_out) *steps_out = steps;
  return 0;
}
"""


@dataclass
class _Part:
    instance: int   # index into JaniModel.instances
    edge: dict


@dataclass
class _Edge:
    """ A (possibly synchronised) transition of the network: one edge per participating automaton instance. """
    action: str
    parts: list[_Part]


_i32p, _i64p, _dblp = ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(ctypes.c_double)
_POLICY_CB = ctypes.CFUNCTYPE(ctypes.c_int, _i32p, ctypes.c_int, _i32p, ctypes.c_int, _dblp)


class _PolicyStruct(ctypes.Structure):
    """ Mirrors jm_policy in _POLICY. """
    _fields_ = [("w", _dblp), ("mask", ctypes.c_int64), ("slot", _i32p), ("keyvar", _i32p), ("keys", _i32p),
                ("nkey", ctypes.c_int32), ("row_off", _i64p), ("row_edge", _i32p), ("row_w", _dblp),
                ("cb", _POLICY_CB)]


class NativePolicy:
    """
    A scheduler for the native batch simulators (simulate, simulate_scores, restart, fixed_effort) that may depend
    on the state and the step count t. Weights over the enabled edges come from, in order:
      - a callback fn(state, t, enabled) -> weights for the enabled edges (any Python function; about 1 µs per
        decision instead of a few ns);
      - a table: key -> {edge index: weight} (or a single edge index, for deterministic choices), where the key is
        the values of `key_vars` (default: all state variables), followed by t when step=True;
      - the default per-action weights (a dict, as for memoryless schedulers), for table misses and callback rows
        that give the enabled edges total weight 0; uniform if those sum to 0 too.
    Depending only on (state, t) keeps importance splitting unbiased: trajectories carry t, so the induced process is
    a Markov chain on (state, t) and clones continue under the same scheduler.
    """
    def __init__(self, model: "JaniModel", default: Optional[dict[str, float]] = None):
        self.model = model
        self.default = model.edge_weight_vector(default)
        self.error: Optional[BaseException] = None
        self._keep: list = []
        self._s = _PolicyStruct(w=_dptr(self.default), mask=-1, cb=_POLICY_CB())

    @classmethod
    def table(cls, model: "JaniModel", rows: dict[tuple, Union[int, dict[int, float]]],
              key_vars: Optional[Sequence[str]] = None, step: bool = True,
              default: Optional[dict[str, float]] = None) -> "NativePolicy":
        p = cls(model, default)
        names = list(key_vars) if key_vars is not None else [v.name for v in model.variables]
        keyvar = np.array([model.index[n] for n in names] + ([-1] if step else []), dtype=np.int32)
        nkey, n = len(keyvar), len(rows)
        keys = np.zeros((max(n, 1), max(nkey, 1)), dtype=np.int32)
        off = np.zeros(n + 1, dtype=np.int64)
        edges: list[int] = []
        weights: list[float] = []
        for r, (key, row) in enumerate(rows.items()):
            if len(key) != nkey:
                raise ValueError(f"policy key {key!r} has {len(key)} values, expected {nkey}")
            keys[r, :nkey] = key
            row = {int(row): 1.0} if not isinstance(row, dict) else row
            edges.extend(int(e) for e in row)
            weights.extend(float(w) for w in row.values())
            off[r + 1] = len(edges)
        edge_arr = np.array(edges or [0], dtype=np.int32)
        if len(edges) and (edge_arr.min() < 0 or edge_arr.max() >= len(model.edges)):
            raise ValueError("policy table refers to an edge index outside the model")
        w_arr = np.array(weights or [0.0], dtype=np.float64)
        cap = 1 << max(4, (2 * n).bit_length())     # load factor <= 1/2
        slot = np.empty(cap, dtype=np.int32)
        keys = np.ascontiguousarray(keys[:, :nkey]) if nkey else keys
        if model.lib.jm_table_fill(n, nkey, _ptr(keys), cap - 1, _ptr(slot)) == -5:
            raise ValueError("duplicate key in policy table")
        p._keep += [keyvar, keys, off, edge_arr, w_arr, slot]
        p._s.mask, p._s.slot, p._s.keyvar, p._s.keys, p._s.nkey = cap - 1, _ptr(slot), _ptr(keyvar), _ptr(keys), nkey
        p._s.row_off, p._s.row_edge, p._s.row_w = _lptr(off), _ptr(edge_arr), _dptr(w_arr)
        p.rows = n
        return p

    @classmethod
    def callback(cls, model: "JaniModel",
                 fn: Callable[[np.ndarray, int, np.ndarray], Sequence[float]],
                 default: Optional[dict[str, float]] = None) -> "NativePolicy":
        """ fn(state, t, enabled edge indices) -> weights; `state` is a read-only view valid only during the call. """
        p = cls(model, default)
        nv = len(model.variables)

        def cb(s, t, en, k, w):
            try:
                state = np.ctypeslib.as_array(s, (nv,))
                state.flags.writeable = False
                np.ctypeslib.as_array(w, (k,))[:] = fn(state, t, np.ctypeslib.as_array(en, (k,)).copy())
                return 0
            except BaseException as e:          # re-raised by the caller once the C batch returns
                p.error = e
                return 1
        p._cb = _POLICY_CB(cb)
        p._s.cb = p._cb
        return p

    @property
    def ref(self):
        return ctypes.byref(self._s)


class JaniModel:
    """ A compiled JANI model. Use NativeJaniSimulator for the Simulator interface. """
    def __init__(self, jani: Union[str, Path, dict], goals: Optional[dict[str, Expr]] = None,
                 constants: Optional[dict[str, Union[int, float, bool]]] = None,
                 importance: Optional[dict[str, Expr]] = None, observables: Optional[dict[str, Expr]] = None):
        """
        goals / importance: named JANI expressions compiled into the library; goals are predicates for the batch
        simulators, importance functions (integer-valued) drive the native splitting methods (splitting.py).
        observables: named real-valued state expressions (state rewards) for simulate_rewards.

        Networks of several automata are composed as in the JANI spec: silent edges (no action) interleave, and an
        edge with an action fires only as part of a synchronisation vector, jointly with one matching edge of every
        participating instance (guards conjoined, probabilities multiplied, assignments combined; two instances
        assigning the same variable in one joint step is an error). For a single automaton, an action that appears
        in no synchronisation vector fires on its own under its own name (as Storm's PRISM export expects).
        """
        model = json.loads(Path(jani).read_text()) if not isinstance(jani, dict) else jani
        self.model_type = model["type"]
        consts = {c["name"]: c["value"] for c in model.get("constants", []) if "value" in c}
        consts.update(constants or {})
        missing = [c["name"] for c in model.get("constants", []) if c["name"] not in consts]
        if missing:
            raise JaniUnsupported(f"undefined constants {missing}")
        self.constants = consts

        automata = {a["name"]: a for a in model["automata"]}
        elements = model.get("system", {}).get("elements") or [{"automaton": a["name"]} for a in model["automata"]]
        names = [el["automaton"] for el in elements]
        self.instances = [automata[n] for n in names]
        self.instance_names = [n if names.count(n) == 1 else f"{n}#{i}" for i, n in enumerate(names)]
        local_names = [v["name"] for a in self.instances for v in a.get("variables", []) if not v.get("transient")]
        global_names = {v["name"] for v in model.get("variables", []) if not v.get("transient")}

        self.variables: list[Variable] = []
        var_types: dict[str, str] = {}
        scopes: list[dict[str, int]] = [dict() for _ in self.instances]   # per-instance: identifier -> slot

        def declare(v: dict, display: str) -> int:
            t = v["type"]
            if t == "bool":
                lo, hi, typ = 0, 1, "bool"
            elif isinstance(t, dict) and t.get("kind") == "bounded" and t.get("base") == "int":
                lo, hi, typ = int(_const_eval(t["lower-bound"], consts)), int(_const_eval(t["upper-bound"], consts)), "int"
            else:
                raise JaniUnsupported(f"variable {v['name']}: unsupported type {t!r}")
            self.variables.append(Variable(display, lo, hi, int(_const_eval(v.get("initial-value", lo), consts))))
            var_types[display] = typ
            return len(self.variables) - 1

        global_slots = {v["name"]: declare(v, v["name"]) for v in model.get("variables", []) if not v.get("transient")}
        for i, a in enumerate(self.instances):
            scopes[i].update(global_slots)
            for v in a.get("variables", []):
                if v.get("transient"):
                    continue
                unique = local_names.count(v["name"]) == 1 and v["name"] not in global_names
                scopes[i][v["name"]] = declare(v, v["name"] if unique else f"{self.instance_names[i]}.{v['name']}")

        self.location_slot: list[Optional[int]] = []
        self.location_names = [[loc["name"] for loc in a["locations"]] for a in self.instances]
        for i, a in enumerate(self.instances):
            locs = self.location_names[i]
            if len(locs) > 1:
                name = "__location" if len(self.instances) == 1 else f"__location.{self.instance_names[i]}"
                self.location_slot.append(len(self.variables))
                self.variables.append(Variable(name, 0, len(locs) - 1, locs.index(a["initial-locations"][0])))
                var_types[name] = "int"
            else:
                self.location_slot.append(None)
        self.index = {v.name: i for i, v in enumerate(self.variables)}
        # Transient variables: per-step temporaries, reset to their initial values at every step. Inside a step's
        # assignment levels they live in extra working slots after the persistent state; everywhere else (guards,
        # probabilities, goals, importance) they read as their initial values.
        self.transients: list[Variable] = []
        transient_init: list[dict[str, int]] = [dict() for _ in self.instances]
        transient_scope: list[dict[str, int]] = [dict() for _ in self.instances]
        # Real transient variables are transition rewards (Buffy's rew_<r>): reset to their initial value at every
        # step, set by edge assignments, and summed over the steps of a run by simulate_rewards. They are write-only:
        # reading one in a guard, probability or assignment is an unknown identifier (JaniUnsupported).
        self.reward_variables: list[str] = []
        reward_init: list[float] = []

        def declare_transient(v: dict, scopes_: list[int]):
            t = v["type"]
            if t == "real":
                if v["name"] in self.reward_variables:
                    raise JaniUnsupported(f"reward variable {v['name']!r} declared twice")
                self.reward_variables.append(v["name"])
                reward_init.append(float(_const_eval(v.get("initial-value", 0.0), consts)))
                return
            if t == "bool":
                lo, hi, typ = 0, 1, "bool"
            elif t == "int":
                lo, hi, typ = -2 ** 31, 2 ** 31 - 1, "int"
            elif isinstance(t, dict) and t.get("kind") == "bounded" and t.get("base") == "int":
                lo, hi, typ = int(_const_eval(t["lower-bound"], consts)), int(_const_eval(t["upper-bound"], consts)), "int"
            else:
                raise JaniUnsupported(f"transient variable {v['name']}: unsupported type {t!r}")
            init = int(_const_eval(v.get("initial-value", 0 if lo <= 0 <= hi else lo), consts))
            slot = len(self.variables) + len(self.transients)
            self.transients.append(Variable(v["name"], lo, hi, init))
            var_types[v["name"]] = typ
            for i in scopes_:
                transient_init[i][v["name"]] = init
                transient_scope[i][v["name"]] = slot

        for v in model.get("variables", []):
            if v.get("transient"):
                declare_transient(v, list(range(len(self.instances))))
        for i, a in enumerate(self.instances):
            for v in a.get("variables", []):
                if v.get("transient"):
                    declare_transient(v, [i])
        # Location transient-values (e.g. PRISM labels exported by Storm): outside assignment levels a transient
        # variable reads as its value in the instance's current location, else its initial value.
        for i, a in enumerate(self.instances):
            slot = self.location_slot[i]
            if slot is not None:
                scopes[i]["__loc"] = slot
                var_types.setdefault(self.variables[slot].name, "int")
            for name in {tv["ref"] for loc in a["locations"] for tv in loc.get("transient-values", [])}:
                if name not in transient_init[i]:
                    raise JaniUnsupported(f"transient-value for unknown transient variable {name!r}")
                expr: Expr = transient_init[i][name]
                for li, loc in reversed(list(enumerate(a["locations"]))):
                    value = next((tv["value"] for tv in loc.get("transient-values", []) if tv["ref"] == name), None)
                    if value is None:
                        continue
                    expr = value if slot is None else {"op": "ite", "if": {"op": "=", "left": "__loc", "right": li},
                                                       "then": value, "else": expr}
                transient_init[i][name] = expr
        self._trs, self._trs_read = [], []   # per instance: inside assignment levels / guards and probabilities
        for i, scope in enumerate(scopes):
            tr = _Translator({**scope, **transient_scope[i]}, consts)
            tr.var_types = {k: var_types[self.variables[slot].name] for k, slot in scope.items()}
            tr.var_types.update({k: var_types[k] for k in transient_scope[i]})
            self._trs.append(tr)
            read = _Translator(scope, {**consts, **transient_init[i]})
            read.var_types = {k: var_types[self.variables[slot].name] for k, slot in scope.items()}
            self._trs_read.append(read)
        global_transients = {v.name: v.initial for v in self.transients}
        if len(self.instances) == 1:   # goals and importance may then refer to labels / location-derived values
            global_transients.update({k: v for k, v in transient_init[0].items() if isinstance(v, dict)})
        global_scope = dict(self.index)
        if len(self.instances) == 1 and self.location_slot[0] is not None:
            global_scope["__loc"] = self.location_slot[0]
        self._tr = _Translator(global_scope, {**consts, **global_transients})   # goals and importance
        self._tr.var_types = {**var_types, "__loc": "int"}

        self.edges = self._compose(model)
        self.edge_actions = [e.action for e in self.edges]
        self.goals = dict(goals or {})
        self.goal_names = list(self.goals)
        self.importance = dict(importance or {})
        self.importance_names = list(self.importance)
        self.observables = dict(observables or {})
        self.observable_names = list(self.observables)
        self._reward_init = reward_init
        source = self._generate()
        self.lib = _compile(source)
        self._bind()

    def _compose(self, model: dict) -> list[_Edge]:
        syncs = model.get("system", {}).get("syncs", [])
        n = len(self.instances)
        edges: list[_Edge] = []
        if n == 1:
            # Keep the automaton's edge order (it fixes the order of choices, which matches Storm's simulator).
            rename = {s["synchronise"][0]: s.get("result") for s in syncs if s["synchronise"][0] is not None}
            for e in self.instances[0]["edges"]:
                act = e.get("action")
                name = "τ" if act is None else (rename.get(act) or ("τ" if act in rename else act))
                edges.append(_Edge(name, [_Part(0, e)]))
            return edges
        for i, a in enumerate(self.instances):
            edges += [_Edge("τ", [_Part(i, e)]) for e in a["edges"] if e.get("action") is None]
        synced = set()
        for v in syncs:
            slots = [(i, act) for i, act in enumerate(v["synchronise"]) if act is not None]
            synced.update(slots)
            choices = [[_Part(i, e) for e in self.instances[i]["edges"] if e.get("action") == act] for i, act in slots]
            for parts in itertools.product(*choices):
                edges.append(_Edge(v.get("result") or "τ", list(parts)))
        dropped = {(self.instance_names[i], e["action"]) for i, a in enumerate(self.instances) for e in a["edges"]
                   if e.get("action") is not None and (i, e["action"]) not in synced}
        if dropped:
            warnings.warn(f"actions in no synchronisation vector can never fire (JANI semantics): {sorted(dropped)}")
        return edges

    # ---- code generation -------------------------------------------------------------------------------------------
    # Code is generated once per automaton edge ("part edge": guard, destination probabilities, one assignment
    # function per index level, location update). A network transition (_Edge) only calls its parts, so code size is
    # additive in the participants, not multiplicative in their destination combinations. A transition's outcome is
    # a mixed-radix index over its parts' destinations; the parts' choices are independent (probabilities multiply).
    def _part_edges(self) -> list[_Part]:
        seen: dict[tuple[int, int], int] = {}
        parts: list[_Part] = []
        self._part_id: list[list[int]] = []
        for e in self.edges:
            ids = []
            for p in e.parts:
                key = (p.instance, id(p.edge))
                if key not in seen:
                    seen[key] = len(parts)
                    parts.append(p)
                ids.append(seen[key])
            self._part_id.append(ids)
        return parts

    def _part_levels(self, p: _Part) -> tuple[dict[int, list[list[tuple[int, Expr]]]],
                                              dict[int, list[list[tuple[int, Expr]]]]]:
        """
        level -> per destination, the (slot, value) assignments at that level; and likewise the (reward variable
        index, value) assignments to reward variables.
        """
        scope = self._trs[p.instance].variables
        levels: dict[int, list[list[tuple[int, Expr]]]] = {}
        rewards: dict[int, list[list[tuple[int, Expr]]]] = {}
        dests = p.edge["destinations"]
        for j, d in enumerate(dests):
            for a in d.get("assignments", []):
                if a["ref"] in self.reward_variables and a["ref"] not in scope:
                    per_dest = rewards.setdefault(int(a.get("index", 0)), [[] for _ in dests])
                    per_dest[j].append((self.reward_variables.index(a["ref"]), a["value"]))
                    continue
                if a["ref"] not in scope:
                    raise JaniUnsupported(f"assignment to unknown variable {a['ref']!r}")
                per_dest = levels.setdefault(int(a.get("index", 0)), [[] for _ in dests])
                per_dest[j].append((scope[a["ref"]], a["value"]))
        for per_dest in list(levels.values()) + list(rewards.values()):
            for writes in per_dest:
                if len({slot for slot, _ in writes}) != len(writes):
                    raise JaniUnsupported("a variable is assigned twice at one assignment level")
        return levels, rewards

    def _generate_parts(self, parts: list[_Part]) -> list[str]:
        out = []
        self._levels_of: list[dict[int, list]] = []
        self._rlevels_of: list[dict[int, list]] = []
        for k, p in enumerate(parts):
            tr_read, tr = self._trs_read[p.instance], self._trs[p.instance]
            slot = self.location_slot[p.instance]
            guard = tr_read.c(p.edge.get("guard", {}).get("exp", True))
            if slot is not None:
                guard = f"(s[{slot}] == {self.location_names[p.instance].index(p.edge['location'])}) && {guard}"
            out.append(f"static inline int pg{k}(const int32_t *s) {{ return {guard}; }}")
            dests = p.edge["destinations"]
            probs = "".join(f" case {j}: return (double)({tr_read.c(d.get('probability', {}).get('exp', 1))});"
                            for j, d in enumerate(dests))
            out.append(f"static double pp{k}(const int32_t *s, int d) {{ switch (d) {{{probs} }} return 0.0; }}")
            levels, rlevels = self._part_levels(p)
            self._levels_of.append(levels)
            self._rlevels_of.append(rlevels)
            for level, per_dest in levels.items():
                cases = "".join(f" case {j}:" + "".join(f" t[{slot_}] = (int32_t)({tr.c(v)});" for slot_, v in w)
                                + " break;" for j, w in enumerate(per_dest) if w)
                out.append(f"static inline void pa{k}_{level}(int32_t *t, const int32_t *s, int d) "
                           f"{{ switch (d) {{{cases} }} }}")
            for level, per_dest in rlevels.items():
                cases = "".join(f" case {j}:" + "".join(f" r[{ri}] = (double)({tr.c(v)});" for ri, v in w)
                                + " break;" for j, w in enumerate(per_dest) if w)
                out.append(f"static inline void pr{k}_{level}(double *r, const int32_t *s, int d) "
                           f"{{ switch (d) {{{cases} }} }}")
            if slot is not None:
                cases = "".join(f" case {j}: t[{slot}] = {self.location_names[p.instance].index(d['location'])}; break;"
                                for j, d in enumerate(dests))
                out.append(f"static inline void pl{k}(int32_t *t, int d) {{ switch (d) {{{cases} }} }}")
        return out

    def _generate_transition(self, i: int, parts: list[_Part]) -> str:
        """
        ce<i>(t, s0, dd, r): applies network transition i with per-part destinations dd (levels in order); if r is not
        NULL, the reward variables it assigns are written to r (read from the same per-level state as the variables).
        """
        ids = self._part_id[i]
        all_levels = sorted({lv for k in ids for lv in list(self._levels_of[k]) + list(self._rlevels_of[k])})
        for lv in all_levels:   # two participants may not write the same variable at the same level
            for of in (self._levels_of, self._rlevels_of):
                seen: set[int] = set()
                for k in ids:
                    slots = {slot for w in of[k].get(lv, []) for slot, _ in w}
                    if slots & seen:
                        raise JaniUnsupported(f"transition {self.edges[i].action}: synchronised edges write the same "
                                              f"variable at level {lv}")
                    seen |= slots
        body = ""
        for n, lv in enumerate(all_levels):
            calls = "".join(f" pa{k}_{lv}(t, SRC, dd[{pi}]);" for pi, k in enumerate(ids) if lv in self._levels_of[k])
            rcalls = "".join(f" pr{k}_{lv}(r, SRC, dd[{pi}]);" for pi, k in enumerate(ids)
                             if lv in self._rlevels_of[k])
            if rcalls:
                calls += f" if (r) {{{rcalls} }}"
            if n == 0 and not self.transients:
                body += calls.replace("SRC", "s0")
            else:
                body += f" {{ int32_t u[NW]; memcpy(u, t, sizeof u);{calls.replace('SRC', 'u')} }}"
        body += "".join(f" pl{k}(t, dd[{pi}]);" for pi, k in enumerate(ids)
                        if self.location_slot[parts[k].instance] is not None)
        return f"static void ce{i}(int32_t *t, const int32_t *s0, const int *dd, double *r) {{{body} }}"

    def _generate(self) -> str:
        tr, nv, ne = self._tr, len(self.variables), len(self.edges)
        parts = self._part_edges()
        nd_part = [len(p.edge["destinations"]) for p in parts]
        nd_edge = [int(np.prod([nd_part[k] for k in ids])) for ids in self._part_id]
        if max(nd_edge + [1]) > 2 ** 30:
            raise JaniUnsupported("too many joint destinations in one synchronised transition")
        max_parts = max([len(ids) for ids in self._part_id] + [1])
        out = [_PRELUDE, f"#define NV {nv}", f"#define NW {nv + len(self.transients)}", f"#define NE {ne}",
               f"#define MAXP {max_parts}", "int jm_nvars(void) { return NV; }", "int jm_nedges(void) { return NE; }"]
        out.append("void jm_init(int32_t *s) {" + "".join(f" s[{i}] = {v.initial};" for i, v in
                                                          enumerate(self.variables)) + " }")
        out += self._generate_parts(parts)
        out += [self._generate_transition(i, parts) for i in range(ne)]
        # Each part guard is evaluated once per state; network transitions combine the cached results.
        out.append(f"int jm_enabled(const int32_t *s, int32_t *out) {{\n  int k = 0; char g[{len(parts)}];")
        out.append("".join(f"  g[{k}] = pg{k}(s);" for k in range(len(parts))))
        for i, ids in enumerate(self._part_id):
            out.append(f"  if ({' && '.join(f'g[{k}]' for k in ids)}) out[k++] = {i};")
        out.append("  return k;\n}")
        flat = [k for ids in self._part_id for k in ids]
        offsets = np.cumsum([0] + [len(ids) for ids in self._part_id])[:-1]
        out.append("static const int jm_nd[NE] = {" + ", ".join(map(str, nd_edge)) + "};")
        out.append("static const int jm_np[NE] = {" + ", ".join(str(len(ids)) for ids in self._part_id) + "};")
        out.append("static const int jm_poff[NE] = {" + ", ".join(map(str, offsets)) + "};")
        out.append(f"static const int jm_pk[{len(flat)}] = {{" + ", ".join(map(str, flat)) + "};")
        out.append(f"static const int jm_pnd[{len(parts)}] = {{" + ", ".join(map(str, nd_part)) + "};")
        out.append(f"static double (*const jm_pp[{len(parts)}])(const int32_t *, int) = {{"
                   + ", ".join(f"pp{k}" for k in range(len(parts))) + "};")
        out.append(f"static void (*const jm_ce[NE])(int32_t *, const int32_t *, const int *, double *) = {{"
                   + ", ".join(f"ce{i}" for i in range(ne)) + "};")
        out.append("int jm_ndest(int e) { return jm_nd[e]; }")
        out.append(r"""static void jm_digits(int e, int d, int *dd) {
  for (int p = 0; p < jm_np[e]; p++) { int nd = jm_pnd[jm_pk[jm_poff[e] + p]]; dd[p] = d % nd; d /= nd; }
}
double jm_prob(const int32_t *s, int e, int d) {
  int dd[MAXP]; double q = 1.0; jm_digits(e, d, dd);
  for (int p = 0; p < jm_np[e]; p++) q *= jm_pp[jm_pk[jm_poff[e] + p]](s, dd[p]);
  return q;
}""")
        bounds = " ".join(f"if (t[{i}] < {v.lower} || t[{i}] > {v.upper}) return -1;"
                          for i, v in enumerate(self.variables + self.transients) if (v.lower, v.upper) != (-2 ** 31, 2 ** 31 - 1))
        init_transients = "".join(f" t[{nv + j}] = {v.initial};" for j, v in enumerate(self.transients))
        init_rewards = "".join(f" r[{j}] = {x!r};" for j, x in enumerate(self._reward_init))
        out.append(f"#define NR {len(self.reward_variables)}")
        out.append("/* r: NULL, or NR reward variables, reset to their initial values and set by the transition */\n"
                   "int jm_apply_r(int32_t *s, int e, int d, double *r) {\n  int32_t t[NW]; int dd[MAXP];\n"
                   f"  if (e < 0 || e >= NE || d < 0 || d >= jm_nd[e]) return -2;\n"
                   f"  memcpy(t, s, NV * sizeof(int32_t));{init_transients}\n"
                   f"  if (r) {{{init_rewards} }}\n"
                   f"  jm_digits(e, d, dd); jm_ce[e](t, s, dd, r);\n  {bounds}\n  memcpy(s, t, NV * sizeof(int32_t));\n"
                   "  return 0;\n}\n"
                   "int jm_apply(int32_t *s, int e, int d) { return jm_apply_r(s, e, d, NULL); }")
        # Sampling: each part's destination in turn by inverse CDF on one uniform, rescaled inside the chosen
        # interval (exact, since u is uniform on that interval given the choice).
        out.append(r"""static int jm_step_r(int32_t *s, int e, double u, double *r) {
  int d = 0, mult = 1;
  for (int p = 0; p < jm_np[e]; p++) {
    int k = jm_pk[jm_poff[e] + p], nd = jm_pnd[k], j = 0;
    if (nd > 1) {
      double acc = 0.0, q = 0.0;
      for (j = 0; j < nd; j++) { q = jm_pp[k](s, j); if (u < acc + q || j == nd - 1) break; acc += q; }
      u = q > 0.0 ? (u - acc) / q : 0.0;
      if (u < 0.0) u = 0.0; if (u >= 1.0) u = 0x1.fffffffffffffp-1;
    }
    d += j * mult; mult *= nd;
  }
  int rc = jm_apply_r(s, e, d, r);
  return rc < 0 ? rc : d;
}
int jm_step(int32_t *s, int e, double u) { return jm_step_r(s, e, u, NULL); }""")
        out.append("int jm_goal(const int32_t *s, int g) {\n  switch (g) {")
        for g, name in enumerate(self.goal_names):
            out.append(f"    case {g}: return {tr.c(self.goals[name])};")
        out.append("  }\n  return 0;\n}")
        out.append("int64_t jm_imp(const int32_t *s, int f) {\n  switch (f) {")
        for f, name in enumerate(self.importance_names):
            out.append(f"    case {f}: return (int64_t)({tr.c(self.importance[name])});")
        out.append("  }\n  return 0;\n}")
        out.append(f"#define NO {len(self.observable_names)}")
        out.append("double jm_obs(const int32_t *s, int f) {\n  switch (f) {")
        for f, name in enumerate(self.observable_names):
            out.append(f"    case {f}: return (double)({tr.c(self.observables[name])});")
        out.append("  }\n  return 0.0;\n}")
        # Batch simulation under a scheduler given as a jm_policy (see _POLICY).
        out.append(_POLICY)
        out.append(r"""
/* Returns the number of runs that reach the goal within the horizon, or -1 (bounds error) / -4 (callback failed). */
int64_t jm_simulate(const int32_t *s0, int64_t n_runs, int horizon, const jm_policy *pol, int goal,
                    uint64_t seed, int64_t *steps_out) {
  uint64_t rng[4], x = seed; for (int i = 0; i < 4; i++) rng[i] = jm_splitmix(&x);
  int64_t hits = 0, steps = 0; int32_t s[NV], en[NE];
  for (int64_t r = 0; r < n_runs; r++) {
    memcpy(s, s0, sizeof s);
    for (int t = 0; t <= horizon; t++) {
      if (jm_goal(s, goal)) { hits++; break; }
      if (t == horizon) break;
      int k = jm_enabled(s, en); if (k == 0) break;
      int e = k > 1 ? jm_pick(pol, s, t, en, k, rng) : en[0];
      if (e == -4) return -4;
      if (jm_step(s, e, jm_uniform(rng)) < 0) return -1;
      steps++;
    }
  }
  if (steps_out) *steps_out = steps;
  return hits;
}

/* Like jm_simulate, but records for each run the maximum of variable score_var and how often each edge was chosen
   at decision points (states with several enabled edges); for cross-entropy / distribution learning. */
int jm_simulate_scores(const int32_t *s0, int64_t n_runs, int horizon, const jm_policy *pol, int score_var,
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
        if ((e = jm_pick(pol, s, t, en, k, rng)) == -4) return -4;
        cnt[e]++;
      }
      if (jm_step(s, e, jm_uniform(rng)) < 0) return -1;
      if (s[score_var] > best) best = s[score_var];
    }
    scores[r] = best;
  }
  return 0;
}

/* Reward runs of exactly `horizon` steps; a deadlock state is kept (as with Storm's deadlock self-loops), earning no
   transition rewards. Per run r: cum[r*NR+j] = sum over the steps of reward variable j (C<=horizon);
   ocum[r*NO+f] = sum over t < horizon of observable f in the state at step t (state rewards, C<=horizon);
   oend[r*NO+f] = observable f at step horizon (I=horizon). If curve is not NULL, it accumulates over the runs, for
   each step t = 0..horizon, the sum and sum of squares of each cumulative reward variable up to t and each observable
   at t: curve[(t*(NR+NO) + i)*2 + {0, 1}] with i < NR for reward variables, NR + f for observables. Returns 0, or
   -1 (bounds error) / -4 (policy callback failed). */
int jm_simulate_rewards(const int32_t *s0, int64_t n_runs, int horizon, const jm_policy *pol, uint64_t seed,
                        double *cum, double *ocum, double *oend, double *curve, int64_t *steps_out) {
  uint64_t rng[4], x = seed; for (int i = 0; i < 4; i++) rng[i] = jm_splitmix(&x);
  int64_t steps = 0; int32_t s[NV], en[NE]; double rw[NR + 1], c[NR + 1], oc[NO + 1];
  for (int64_t r = 0; r < n_runs; r++) {
    memcpy(s, s0, sizeof s);
    for (int j = 0; j < NR; j++) c[j] = 0.0;
    for (int f = 0; f < NO; f++) oc[f] = 0.0;
    int dead = 0;
    for (int t = 0; ; t++) {
      if (curve) {
        double *cv = curve + (int64_t)t * (NR + NO) * 2;
        for (int j = 0; j < NR; j++) { cv[2 * j] += c[j]; cv[2 * j + 1] += c[j] * c[j]; }
        for (int f = 0; f < NO; f++) { double o = jm_obs(s, f); cv[2 * (NR + f)] += o; cv[2 * (NR + f) + 1] += o * o; }
      }
      if (t == horizon) break;
      for (int f = 0; f < NO; f++) oc[f] += jm_obs(s, f);
      if (dead) continue;
      int k = jm_enabled(s, en);
      if (k == 0) { dead = 1; continue; }
      int e = k > 1 ? jm_pick(pol, s, t, en, k, rng) : en[0];
      if (e == -4) return -4;
      if (jm_step_r(s, e, jm_uniform(rng), rw) < 0) return -1;
      for (int j = 0; j < NR; j++) c[j] += rw[j];
      steps++;
    }
    for (int j = 0; j < NR; j++) cum[r * NR + j] = c[j];
    for (int f = 0; f < NO; f++) { ocum[r * NO + f] = oc[f]; oend[r * NO + f] = jm_obs(s, f); }
  }
  if (steps_out) *steps_out = steps;
  return 0;
}""")
        out.append(_SPLITTING)
        return "\n".join(out) + "\n"

    def _bind(self):
        lib, i32p, dbl = self.lib, ctypes.POINTER(ctypes.c_int32), ctypes.c_double
        lib.jm_init.argtypes = [i32p]
        lib.jm_enabled.argtypes, lib.jm_enabled.restype = [i32p, i32p], ctypes.c_int
        lib.jm_prob.argtypes, lib.jm_prob.restype = [i32p, ctypes.c_int, ctypes.c_int], dbl
        lib.jm_step.argtypes, lib.jm_step.restype = [i32p, ctypes.c_int, dbl], ctypes.c_int
        lib.jm_goal.argtypes, lib.jm_goal.restype = [i32p, ctypes.c_int], ctypes.c_int
        lib.jm_obs.argtypes, lib.jm_obs.restype = [i32p, ctypes.c_int], dbl
        lib.jm_apply.argtypes, lib.jm_apply.restype = [i32p, ctypes.c_int, ctypes.c_int], ctypes.c_int
        lib.jm_ndest.argtypes, lib.jm_ndest.restype = [ctypes.c_int], ctypes.c_int
        lib.jm_apply_r.argtypes = [i32p, ctypes.c_int, ctypes.c_int, ctypes.POINTER(dbl)]
        lib.jm_apply_r.restype = ctypes.c_int
        polp = ctypes.POINTER(_PolicyStruct)
        lib.jm_table_fill.argtypes = [ctypes.c_int64, ctypes.c_int, i32p, ctypes.c_int64, i32p]
        lib.jm_table_fill.restype = ctypes.c_int
        lib.jm_simulate.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, polp, ctypes.c_int,
                                    ctypes.c_uint64, ctypes.POINTER(ctypes.c_int64)]
        lib.jm_simulate.restype = ctypes.c_int64
        lib.jm_simulate_scores.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, polp, ctypes.c_int,
                                           ctypes.c_uint64, i32p, i32p]
        lib.jm_simulate_scores.restype = ctypes.c_int
        dblp_ = ctypes.POINTER(dbl)
        lib.jm_simulate_rewards.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, polp, ctypes.c_uint64, dblp_, dblp_,
                                            dblp_, dblp_, ctypes.POINTER(ctypes.c_int64)]
        lib.jm_simulate_rewards.restype = ctypes.c_int
        i64p, dblp = ctypes.POINTER(ctypes.c_int64), ctypes.POINTER(dbl)
        lib.jm_restart.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, polp, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   i64p, i32p, ctypes.c_uint64, ctypes.c_int64, dblp, i64p]
        lib.jm_restart.restype = ctypes.c_int
        lib.jm_fixed_effort.argtypes = [i32p, ctypes.c_int64, ctypes.c_int, polp, ctypes.c_int, ctypes.c_int,
                                        ctypes.c_int, i64p, i32p, ctypes.c_uint64, dblp, i32p, i64p]
        lib.jm_fixed_effort.restype = ctypes.c_int

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

    def successors(self, s: np.ndarray, edge: int, rewards: bool = False) -> list[tuple]:
        """
        The probabilistic outcomes of taking `edge` from s: [(probability, successor state)], or with rewards
        [(probability, successor state, reward variable values)].
        """
        out = []
        for d in range(self.lib.jm_ndest(int(edge))):
            t, r = s.copy(), np.zeros(max(len(self.reward_variables), 1))
            if self.lib.jm_apply_r(_ptr(t), int(edge), d, _dptr(r) if rewards else None) < 0:
                raise RuntimeError(f"edge {edge} ({self.edge_actions[edge]}): assignment out of variable bounds")
            p = self.lib.jm_prob(_ptr(s), int(edge), d)
            out.append((p, t, r[:len(self.reward_variables)]) if rewards else (p, t))
        return out

    def observable(self, s: np.ndarray, name: str) -> float:
        return self.lib.jm_obs(_ptr(s), self.observable_names.index(name))

    def goal(self, s: np.ndarray, name: str) -> bool:
        return bool(self.lib.jm_goal(_ptr(s), self.goal_names.index(name)))

    def policy(self, scheduler: "Scheduling") -> NativePolicy:
        """ A NativePolicy from per-action weights (memoryless; None = uniform) or an existing NativePolicy. """
        if isinstance(scheduler, NativePolicy):
            if scheduler.model is not self:
                raise ValueError("the policy was built for another model")
            return scheduler
        return NativePolicy(self, scheduler)

    def simulate(self, n_runs: int, horizon: int, goal: str, scheduler: "Scheduling" = None,
                 seed: int = 1, start: Optional[np.ndarray] = None) -> tuple[int, int]:
        """ Native batch runs under a scheduler (see policy()); returns (goal hits, total steps). """
        pol = self.policy(scheduler)
        s0 = self.initial_state() if start is None else np.ascontiguousarray(start, dtype=np.int32)
        steps = ctypes.c_int64(0)
        hits = self.lib.jm_simulate(_ptr(s0), n_runs, horizon, pol.ref, self.goal_names.index(goal), seed,
                                    ctypes.byref(steps))
        _check(hits if hits < 0 else 0, pol)
        return hits, steps.value

    def simulate_scores(self, n_runs: int, horizon: int, score_var: str,
                        scheduler: Union[np.ndarray, NativePolicy], seed: int = 1) -> tuple[np.ndarray, np.ndarray]:
        """
        Native batch runs under per-edge weights or a NativePolicy; returns (max of score_var per run, per-run edge
        choice counts).
        """
        if isinstance(scheduler, NativePolicy):
            pol = self.policy(scheduler)
        else:
            pol = NativePolicy(self)
            pol.default = np.ascontiguousarray(scheduler, dtype=np.float64)
            pol._s.w = _dptr(pol.default)
        scores = np.empty(n_runs, dtype=np.int32)
        counts = np.empty((n_runs, len(self.edges)), dtype=np.int32)
        _check(self.lib.jm_simulate_scores(_ptr(self.initial_state()), n_runs, horizon, pol.ref,
                                           self.index[score_var], seed, _ptr(scores), _ptr(counts)), pol)
        return scores, counts

    def simulate_rewards(self, n_runs: int, horizon: int, scheduler: "Scheduling" = None, seed: int = 1,
                         curve: bool = False, start: Optional[np.ndarray] = None) -> "RewardRuns":
        """
        Native batch runs of exactly `horizon` steps under a scheduler (see policy()), for expected-reward queries:
        per run, the total of each reward variable (transition rewards, C<=horizon), the sum of each observable over
        steps 0..horizon-1 (state rewards, C<=horizon) and its value at step horizon (I=horizon). With curve, also the
        per-step means and variances over the runs, for every bound 0..horizon at once.
        """
        clash = set(self.reward_variables) & set(self.observable_names)
        if curve and clash:
            raise ValueError(f"observables named like reward variables: {sorted(clash)}")
        pol = self.policy(scheduler)
        s0 = self.initial_state() if start is None else np.ascontiguousarray(start, dtype=np.int32)
        nr, no = len(self.reward_variables), len(self.observable_names)
        cum, ocum, oend = np.empty((n_runs, nr)), np.empty((n_runs, no)), np.empty((n_runs, no))
        cv = np.zeros((horizon + 1, nr + no, 2)) if curve else None
        steps = ctypes.c_int64(0)
        _check(self.lib.jm_simulate_rewards(_ptr(s0), n_runs, horizon, pol.ref, seed, _dptr(cum), _dptr(ocum),
                                            _dptr(oend), _dptr(cv) if cv is not None else None, ctypes.byref(steps)),
               pol)
        means = variances = None
        if cv is not None:
            m = cv[:, :, 0] / n_runs
            v = np.maximum(cv[:, :, 1] / n_runs - m ** 2, 0.0) * n_runs / max(n_runs - 1, 1)
            names = self.reward_variables + self.observable_names
            means = {name: m[:, i] for i, name in enumerate(names)}
            variances = {name: v[:, i] for i, name in enumerate(names)}
        return RewardRuns(horizon, n_runs, steps.value,
                          {name: cum[:, j] for j, name in enumerate(self.reward_variables)},
                          {name: ocum[:, f] for f, name in enumerate(self.observable_names)},
                          {name: oend[:, f] for f, name in enumerate(self.observable_names)}, means, variances)

    def edge_weight_vector(self, action_weights: Optional[dict[str, float]]) -> np.ndarray:
        return np.array([(action_weights or {}).get(a, 0.0) for a in self.edge_actions], dtype=np.float64)

    def restart(self, n_runs: int, horizon: int, goal: str, importance: str, thresholds: list[int],
                factors: list[int], scheduler: "Scheduling" = None, seed: int = 1,
                max_trajectories: int = 10_000_000) -> tuple[np.ndarray, int]:
        """ n_runs independent RESTART runs (see jm_restart); returns (per-run estimates, total steps). """
        thr = np.ascontiguousarray(thresholds, dtype=np.int64)
        fac = np.ascontiguousarray(factors, dtype=np.int32)
        if len(thr) != len(fac) or np.any(np.diff(thr) <= 0) or np.any(fac < 1):
            raise ValueError("need increasing thresholds and factors >= 1 of the same length")
        pol, out, steps = self.policy(scheduler), np.empty(n_runs), ctypes.c_int64(0)
        rc = self.lib.jm_restart(_ptr(self.initial_state()), n_runs, horizon, pol.ref, self.goal_names.index(goal),
                                 self.importance_names.index(importance), len(thr), _lptr(thr), _ptr(fac), seed,
                                 max_trajectories, _dptr(out), ctypes.byref(steps))
        _check(rc, pol)
        return out, steps.value

    def fixed_effort(self, n_runs: int, horizon: int, goal: str, importance: str, thresholds: list[int],
                     efforts: list[int], scheduler: "Scheduling" = None, seed: int = 1,
                     level_successes: bool = False):
        """
        n_runs independent fixed-effort runs (see jm_fixed_effort); efforts has len(thresholds)+1 entries.
        Returns (per-run estimates, total steps) or, with level_successes, also the (n_runs, levels) success counts.
        """
        thr = np.ascontiguousarray(thresholds, dtype=np.int64)
        eff = np.ascontiguousarray(efforts, dtype=np.int32)
        if len(eff) != len(thr) + 1 or np.any(np.diff(thr) <= 0) or np.any(eff < 1):
            raise ValueError("need increasing thresholds and len(thresholds)+1 positive efforts")
        pol, out, steps = self.policy(scheduler), np.empty(n_runs), ctypes.c_int64(0)
        succ = np.empty((n_runs, len(eff)), dtype=np.int32) if level_successes else None
        rc = self.lib.jm_fixed_effort(_ptr(self.initial_state()), n_runs, horizon, pol.ref,
                                      self.goal_names.index(goal), self.importance_names.index(importance), len(thr),
                                      _lptr(thr), _ptr(eff), seed, _dptr(out),
                                      _ptr(succ) if succ is not None else None, ctypes.byref(steps))
        _check(rc, pol)
        return (out, steps.value, succ) if level_successes else (out, steps.value)


@dataclass
class RewardRuns:
    """
    Samples from JaniModel.simulate_rewards. cumulative: reward variable -> per-run total (C<=horizon);
    state_cumulative / final: observable -> per-run sum over steps 0..horizon-1 / value at step horizon (I=horizon).
    curve_mean / curve_var (with curve=True): name -> per-step mean / variance over the runs, index t = 0..horizon
    (cumulative up to t for reward variables, the value at t for observables).
    """
    horizon: int
    runs: int
    steps: int
    cumulative: dict[str, np.ndarray]
    state_cumulative: dict[str, np.ndarray]
    final: dict[str, np.ndarray]
    curve_mean: Optional[dict[str, np.ndarray]] = None
    curve_var: Optional[dict[str, np.ndarray]] = None


def mean_ci(x: np.ndarray, level: float = 0.99) -> tuple[float, float]:
    """ Sample mean and the half-width of its normal-approximation confidence interval. """
    z = NormalDist().inv_cdf(0.5 + level / 2)
    return float(np.mean(x)), float(z * np.std(x, ddof=1) / np.sqrt(len(x))) if len(x) > 1 else float("inf")


def _ptr(a: np.ndarray):
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_int32 if a.dtype == np.int32 else ctypes.c_double))


def _dptr(a: np.ndarray):
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_double))


def _lptr(a: np.ndarray):
    return a.ctypes.data_as(ctypes.POINTER(ctypes.c_int64))


def _check(rc: int, pol: Optional[NativePolicy] = None) -> None:
    if rc == -4 and pol is not None and pol.error is not None:
        err, pol.error = pol.error, None
        raise err
    if rc == -1:
        raise RuntimeError("assignment out of variable bounds during simulation")
    if rc == -2:
        raise RuntimeError("RESTART: trajectory limit exceeded (splitting factors too large?) or out of memory")
    if rc == -3:
        raise ValueError("at most 64 splitting levels are supported")
    if rc == -4:
        raise RuntimeError("policy callback failed")


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
