"""Read a PRISM ``.props`` file and turn each LTL property into an LDBA for LCRL.

A ``.props`` file holds one PRISM property per line, e.g.

    P=? [ F ("done" & odrops>=THRESH) ]

``PrismProperties`` reads such a file (the one sharing the ``.pm`` model's base
name), and for each property:

  1. strips the probability wrapper (``P=? [...]``, ``P>=0.5 [...]``, ``Pmax=? [...]``);
  2. translates the inner PRISM path formula to OWL LTL syntax, lifting each
     atomic proposition -- a quoted label reference ``"done"`` or a relational
     expression ``odrops>=THRESH`` -- to a named OWL atomic proposition and
     recording how to decide it on an MDP state;
  3. converts the LTL to an LCRL-compatible LDBA via OWL (see ``owl.py``);
  4. exposes a ``label_fn`` that maps an MDP state to the true propositions, so
     the whole thing plugs straight into ``PrismBlackBoxMDP``.

Only the *unbounded* LTL fragment OWL supports is handled; PRISM's step-bounded
operators (``F<=T``, ``G<=T``, ``F=T`` ...) and reward properties raise a clear
error.
"""

import os
import re

from src.netmdp.lcrl.owl import find_owl, ltl_to_ldba


class PropertyError(ValueError):
    """A property that cannot be handled (bounded, reward, malformed, ...)."""


# --------------------------------------------------------------------------- #
# atomic propositions
# --------------------------------------------------------------------------- #
class AtomicProposition:
    """One OWL atomic proposition and how to decide it on an MDP state."""

    def __init__(self, name, kind, source, predicate):
        self.name = name          # OWL AP identifier
        self.kind = kind          # "label" or "relation"
        self.source = source      # original PRISM text
        self.predicate = predicate  # (state_dict, declared_labels) -> bool

    def __repr__(self):
        return f"AP({self.name}={self.source!r})"


class ParsedProperty:
    """A single parsed PRISM property and its LDBA/label_fn."""

    def __init__(self, raw, prob_op, threshold, ltl, atoms, owl_path):
        self.raw = raw
        self.prob_op = prob_op          # 'max' | 'min' | 'query' | '>=' | '<=' | '>' | '<'
        self.threshold = threshold      # float or None
        self.ltl = ltl                  # OWL-syntax LTL string
        self.atoms = atoms              # list[AtomicProposition]
        self._owl_path = owl_path
        self._ldba = None

    @property
    def ldba(self):
        """The LCRL-compatible LDBA (built lazily via OWL)."""
        if self._ldba is None:
            if not self._owl_path:
                raise PropertyError(
                    "No OWL binary configured; pass owl_path=... (or set $OWL_PATH)."
                )
            self._ldba = ltl_to_ldba(self.ltl, self._owl_path)
        return self._ldba

    def label_fn(self):
        """Return ``fn(state_dict, declared_labels) -> [ap names true here]``."""
        atoms = self.atoms

        def fn(state, declared_labels=()):
            return [a.name for a in atoms if a.predicate(state, declared_labels)]

        return fn

    def __repr__(self):
        return f"ParsedProperty(ltl={self.ltl!r}, atoms={self.atoms})"


# --------------------------------------------------------------------------- #
# the reader
# --------------------------------------------------------------------------- #
class PrismProperties:
    def __init__(self, props_path=None, pm_path=None, constants=None, owl_path=None):
        if props_path is None:
            if pm_path is None:
                raise ValueError("provide props_path or pm_path")
            props_path = os.path.splitext(pm_path)[0] + ".props"
        self.props_path = props_path
        self.constants = dict(constants or {})
        self.owl_path = owl_path or find_owl()
        self.properties = []      # successfully parsed
        self.errors = []          # (raw_line, PropertyError)
        self._parse()

    def _parse(self):
        for raw in _property_lines(self.props_path):
            try:
                self.properties.append(self._parse_property(raw))
            except PropertyError as e:
                self.errors.append((raw, e))

    def __len__(self):
        return len(self.properties)

    def __getitem__(self, index):
        return self.properties[index]

    def ldba(self, index):
        return self.properties[index].ldba

    def label_fn(self, index):
        return self.properties[index].label_fn()

    # -- per-property translation ----------------------------------------- #
    def _parse_property(self, raw):
        prob_op, threshold, inner = _split_wrapper(raw)
        _reject_bounded(inner, raw)
        ltl, atoms = self._translate(inner)
        return ParsedProperty(raw, prob_op, threshold, ltl, atoms, self.owl_path)

    def _translate(self, inner):
        """PRISM path formula -> (OWL LTL string, [AtomicProposition])."""
        atoms = []              # ordered unique atoms
        by_source = {}          # source text -> AP name
        s = inner

        def fresh(kind, source, predicate, name=None):
            if source in by_source:
                return by_source[source]
            name = name or f"p{len(atoms)}"
            ap = AtomicProposition(name, kind, source, predicate)
            atoms.append(ap)
            by_source[source] = name
            return name

        # 1. quoted label references:  "done" -> AP `done`
        def repl_label(m):
            name = m.group(1)
            ap_name = _sanitize(name)
            return " " + fresh(
                "label", f'"{name}"',
                (lambda st, decl, n=name: n in decl),
                name=ap_name,
            ) + " "

        s = re.sub(r'"([^"]+)"', repl_label, s)

        # 2. relational atoms:  odrops>=THRESH -> AP `pK`
        def repl_rel(m):
            source = m.group(0).strip()
            pred = _relation_predicate(source, self.constants)
            return " " + fresh("relation", source, pred) + " "

        s = re.sub(_RELATION_RE, repl_rel, s)

        # 3. logical operators: PRISM -> OWL
        s = s.replace("<=>", " <-> ").replace("=>", " -> ")

        ltl = _normalise_spaces(s)
        _check_translated(ltl, inner)
        return ltl, atoms


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
# a relational atom: term CMP term, where a term is an identifier or a number
_TERM = r"[A-Za-z_][\w.]*|\d+"
_RELATION_RE = re.compile(rf"(?:{_TERM})\s*(?:<=|>=|!=|<|>|=)\s*(?:{_TERM})")

# PRISM step-bounded temporal operators OWL cannot translate
_BOUNDED_RE = re.compile(r"(?:\b[FGU]\s*(?:<=|>=|<|>|=)|\b[FGU]\s*\[)|<=\s*\(|=\s*T\b")


def _property_lines(path):
    """Yield the non-comment, non-blank property lines of a .props file."""
    with open(path) as fh:
        text = fh.read()
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)   # block comments
    for line in text.splitlines():
        line = re.sub(r"//.*$", "", line).strip()        # line comments
        if line:
            yield line


def _split_wrapper(raw):
    """Return (prob_op, threshold, inner_path_formula)."""
    if re.match(r"^\s*R", raw):
        raise PropertyError("reward properties (R[...]) are not supported")
    m = re.match(
        r"^\s*P(min|max)?\s*(=\s*\?|(>=|<=|>|<)\s*([0-9.]+))\s*\[\s*(.*?)\s*\]\s*$",
        raw,
    )
    if not m:
        raise PropertyError(f"could not parse property wrapper: {raw!r}")
    minmax, _q, cmp_op, thresh, inner = m.groups()
    if cmp_op:
        prob_op, threshold = cmp_op, float(thresh)
    else:
        prob_op = {"min": "min", "max": "max"}.get(minmax, "query")
        threshold = None
    if not inner:
        raise PropertyError(f"empty path formula: {raw!r}")
    return prob_op, threshold, inner


def _reject_bounded(inner, raw):
    if _BOUNDED_RE.search(inner):
        raise PropertyError(
            "step-bounded temporal operators (F<=T, G<=T, F=T, ...) are not "
            f"supported by the OWL LTL->LDBA translation: {raw!r}"
        )


def _relation_predicate(source, constants):
    """Build ``(state, declared) -> bool`` for a PRISM relational atom."""
    expr = re.sub(r"(?<![<>=!])=(?!=)", "==", source)   # PRISM '=' -> Python '=='
    code = compile(expr, "<relation>", "eval")
    consts = dict(constants)

    def pred(state, declared_labels=()):
        env = {}
        env.update(consts)
        env.update(state)
        try:
            return bool(eval(code, {"__builtins__": {}}, env))
        except NameError as e:
            raise PropertyError(
                f"relational atom {source!r} references an unknown "
                f"variable/constant: {e}. Pass it via `constants` or include the "
                f"variable in the MDP state."
            )

    return pred


def _sanitize(name):
    n = re.sub(r"\W", "_", name)
    return n if re.match(r"[A-Za-z_]", n) else "l_" + n


def _normalise_spaces(s):
    return re.sub(r"\s+", " ", s).strip()


def _check_translated(ltl, inner):
    """After lifting atoms, only APs and LTL operators should remain."""
    leftover = re.sub(r"[A-Za-z_]\w*|[FGXURWM&|!()<>\-\s]", "", ltl)
    if leftover:
        raise PropertyError(
            f"could not fully translate PRISM formula {inner!r} to LTL; "
            f"unhandled tokens: {leftover!r}"
        )
