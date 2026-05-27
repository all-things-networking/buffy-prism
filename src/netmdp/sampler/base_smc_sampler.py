from stormpy.simulator import Simulator

from src.netmdp.prism_utils.prism_utils import *
from src.netmdp.sampler.sampler import Sampler


class BaseSMCSampler(Sampler):
    def __init__(self, model_name: str, program: PrismProgram, phi: str, trace_len: int):
        super().__init__()
        self.model_name = model_name
        self.program = program
        self.phi = phi
        # self.true_phi_property = stormpy.parse_properties(f"P>=1 [ {phi} ]", program)
        self.trace_len = trace_len

    def __str__(self):
        return "Base SMC sampler [model={}]".format(self.model_name)

    def trace_sat_property(self, trace_name, trace, trace_len) -> bool:
        trace_program = build_prism_program_from_trace(self.program, trace_name, trace, trace_len)
        true_phi_property = stormpy.parse_properties(f"P>=1 [ {self.phi} ]", trace_program)
        model = stormpy.build_model(trace_program, true_phi_property)
        results = stormpy.model_checking(model, true_phi_property[0])
        result = results.at(model.initial_states[0])
        return result

    def make_program_simulator(self):
        options = stormpy.BuilderOptions()
        options.set_build_state_valuations()
        options.set_build_all_labels()
        model = stormpy.build_sparse_model_with_options(self.program, options)
        simulator = stormpy.simulator.create_simulator(model)
        simulator.set_observation_mode(stormpy.simulator.SimulatorObservationMode.PROGRAM_LEVEL)
        return simulator

    def sample(self) -> float:
        simulator = self.make_program_simulator()
        t = 0
        state, _, _ = simulator.restart()
        trace = [state]
        while t < self.trace_len:
            t += 1
            state, _, _ = simulator.step()
            trace.append(state)
        if self.trace_sat_property(f"trace_lte_{t}", trace, t):
            return 1
        else:
            return 0