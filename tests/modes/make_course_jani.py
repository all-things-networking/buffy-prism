"""
Builds the STAT 535C FQ-CoDel experiment model for the Modest Toolset (modes):
  1. Resolves the arrival nondeterminism of tests/models/fqcodel_5i_mdp_535c.pm with the memoryless "Weibull" traffic
     scheduler used by the course samplers (weights for 0..4 arrivals per queue per time step), giving a DTMC.
  2. Exports the DTMC and the experiment properties to JANI via stormpy.
  3. Exports the MDP itself (arrivals left nondeterministic, one action name per arrival count) to JANI as well, for
     scheduler synthesis / learning (Pmax over traffic schedulers).

Usage: PYTHONPATH=. python tests/modes/make_course_jani.py
"""
import json
import re
from pathlib import Path

import stormpy

MODELS = Path("tests/models")
MDP = MODELS / "fqcodel_5i_mdp_535c.pm"
DTMC = MODELS / "fqcodel_5i_weibull_dtmc_535c.pm"
JANI = Path("tests/modes/fqcodel_5i_weibull_dtmc_535c.jani")
JANI_MDP = Path("tests/modes/fqcodel_5i_mdp_535c.jani")
JANI_MDP_STEPS = Path("tests/modes/fqcodel_5i_mdp_535c_steps.jani")

WEIBULL = [0.4, 0.39, 0.14, 0.05, 0.02]  # P(k arrivals), k = 0..4, as in base_symbolic_smc_sampler
HORIZON = 154                            # simulator steps, as in the course experiments
THRESHOLDS = [2, 3, 4, 5, 8, 9]          # "(true) U<=154 (iq5_deqs_bl>k)"; k+1 is the course goal_deq
HYPOTHESES = {2: 0.70, 4: 0.011, 8: 0.00015}  # course experiments 1-3: k -> theta


def reach(k: int) -> dict:
    """ P(true U<=HORIZON iq5_deqs_bl > k) (Pmax = Pmin for a DTMC). """
    goal = {"op": ">", "left": "iq5_deqs_bl", "right": k}
    return {"op": "Pmax", "exp": {"op": "U", "left": True, "right": goal, "step-bounds": {"upper": HORIZON}}}


def jani_properties() -> list[dict]:
    props = [{"name": f"p_gt{k}",
              "expression": {"op": "filter", "fun": "values", "states": {"op": "initial"}, "values": reach(k)}}
             for k in THRESHOLDS]
    props += [{"name": f"h_gt{k}",
               "expression": {"op": "filter", "fun": "\u2200", "states": {"op": "initial"},
                              "values": {"op": ">", "left": reach(k), "right": theta}}}
              for k, theta in HYPOTHESES.items()]
    # Importance function of the course samplers (ImportanceFQCodel); modes' --ifun-prop needs a named, bare state
    # expression rather than a filter.
    props.append({"name": "imp", "expression": "iq5_deqs_bl"})
    return props

ARRIVAL = re.compile(r"^\s*\[REC_PKT_ARR_IQ(\d)_K(\d)\]\s*(.*?)\s*->\s*(.*?)\s*;\s*$")


def resolve_arrivals(prism: str) -> str:
    """ Replaces each queue's five labelled arrival commands by one probabilistic command. """
    groups, out = {}, []
    for line in prism.splitlines():
        m = ARRIVAL.match(line)
        if not m:
            out.append(line)
            continue
        q, k, guard, update = int(m[1]), int(m[2]), m[3], m[4]
        if q not in groups:
            groups[q] = {"guard": guard, "updates": {}}
            out.append(f"@@ARRIVALS_IQ{q}@@")
        assert groups[q]["guard"] == guard, f"IQ{q}: arrival commands have different guards"
        groups[q]["updates"][k] = update
    assert sorted(groups) == [1, 2, 3, 4, 5]
    text = "\n".join(out)
    for q, g in groups.items():
        assert sorted(g["updates"]) == list(range(len(WEIBULL)))
        branches = " + ".join(f"{w}:{g['updates'][k]}" for k, w in enumerate(WEIBULL))
        text = text.replace(f"@@ARRIVALS_IQ{q}@@", f"\t[] {g['guard']} -> {branches};")
    text, n = re.subn(r"^mdp\s*$", "dtmc", text, count=1, flags=re.MULTILINE)
    assert n == 1
    return text


def add_step_counter(model: dict) -> dict:
    """
    Adds a global step counter `steps` in [0, HORIZON] incremented (saturating) on every edge, so that memoryless
    schedulers over the extended state are step-count aware, as step-bounded objectives require (modes' LSS and
    Q-learning only consider memoryless schedulers).
    """
    model["variables"].append({"name": "steps", "type": {"kind": "bounded", "base": "int", "lower-bound": 0,
                                                         "upper-bound": HORIZON}, "initial-value": 0})
    increment = {"ref": "steps", "value": {"op": "min", "left": {"op": "+", "left": "steps", "right": 1},
                                           "right": HORIZON}}
    for automaton in model["automata"]:
        for edge in automaton["edges"]:
            for destination in edge["destinations"]:
                destination.setdefault("assignments", []).append(dict(increment))
    return model


def export_jani(prism_path: Path, jani_path: Path, step_counter: bool = False):
    program = stormpy.parse_prism_program(str(prism_path))
    jani, _ = program.to_jani([])
    model = json.loads(str(jani))
    # JANI properties may only refer to global variables; the single PRISM module's variables are exported as
    # automaton-local, so move them to the global scope.
    for automaton in model["automata"]:
        model.setdefault("variables", []).extend(automaton.pop("variables", []))
    model["properties"] = jani_properties()
    if step_counter:
        model = add_step_counter(model)
    jani_path.write_text(json.dumps(model, indent=1))
    print(f"wrote {jani_path} with properties {[p['name'] for p in model['properties']]}")


def main():
    DTMC.write_text("// GENERATED by tests/modes/make_course_jani.py from fqcodel_5i_mdp_535c.pm:\n"
                    f"// arrival nondeterminism resolved by the Weibull traffic scheduler {WEIBULL}\n"
                    + resolve_arrivals(MDP.read_text()) + "\n")
    export_jani(DTMC, JANI)
    export_jani(MDP, JANI_MDP)
    export_jani(MDP, JANI_MDP_STEPS, step_counter=True)


if __name__ == "__main__":
    main()
