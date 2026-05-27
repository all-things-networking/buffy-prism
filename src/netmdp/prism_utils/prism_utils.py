import os
import tempfile

import stormpy
from stormpy import PrismProgram


def build_prism_program_from_trace(prism_program, trace_name, trace, trace_len: int) -> PrismProgram:
    commands = []
    variables = dict()
    var_decls = []
    for m in prism_program.modules:
        for v in m.integer_variables:
            variables[v.name] = v.expression_variable.get_expression()
            var_decls.append(v.__str__())
        for v in m.boolean_variables:
            variables[v.name] = v.expression_variable.get_expression()
            var_decls.append(v.__str__())
    var_decls.append(f"ttrace: [0..{trace_len + 1}] init 0;")
    prev_state = trace[0]
    for t, state in enumerate(trace[1:], start=1):
        guards = []
        assignments = []
        for v in variables.keys():
            guards.append(f"({v}={prev_state[v]})")
            assignments.append(f"({v}'={state[v]})")
        prev_state = state
        guard_w_time = " & ".join(guards) + f" & (ttrace={t - 1})"
        assigment_w_time = " & ".join(assignments) + f" & (ttrace'={t})"
        commands.append(f"[] {guard_w_time} -> 1: {assigment_w_time};")
        if t == len(trace) - 1:
            loop_guards = []
            for v in variables.keys():
                loop_guards.append(f"({v}={state[v]})")
            loop_guard_w_time = " & ".join(loop_guards) + f" & (ttrace={t})"
            loop_guard_w_time_1 = " & ".join(loop_guards) + f" & (ttrace={t + 1})"
            loop_assigment_w_time = " & ".join(assignments) + f" & (ttrace'={t + 1})"
            commands.append(f"[] {loop_guard_w_time} -> 1: {loop_assigment_w_time} ;")
            commands.append(f"[] {loop_guard_w_time_1} -> 1: {loop_assigment_w_time} ;")
    labels = []
    for l in prism_program.labels:
        labels.append(f"label \"{l.name}\" = {l.expression};")
    trace_prism_module = f"dtmc\n\t\nmodule {trace_name}\n\n\t{"\n\t".join(var_decls)}\n\n\t{"\n\t".join(commands)}\n\t\nendmodule\n\n{"\n".join(labels)}"

    tf = tempfile.NamedTemporaryFile(delete=False)
    tf.seek(0)
    tf.write(trace_prism_module.encode("utf-8"))
    f_name = tf.name
    tf.close()
    trace_prism_program = stormpy.parse_prism_program(f_name)
    os.unlink(tf.name)
    return trace_prism_program