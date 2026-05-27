import random

import stormpy
from stormpy import PrismProgram
from stormpy.simulator import Simulator

from src.netmdp.sampler.base_symbolic_smc_sampler import BaseSymbolicSMCSampler
from src.netmdp.sampler.sampler import SamplerError
from src.netmdp.sampler.splitting.importance_function import ImportanceFunction


class SplittingSMCSampler(BaseSymbolicSMCSampler):
    def __init__(self, model_name: str, program: PrismProgram, phi: str, trace_len: int,
                 goal_deq: int,
                 importance: ImportanceFunction,
                 expected_success_effort = None,
                 all_levels = None,
                 const_splits = None,
                 max_level = None):
        super().__init__(model_name, program, phi, trace_len, goal_deq)
        self.importance = importance
        if expected_success_effort and (all_levels is None or const_splits is None or max_level is None):
            self.levels, self.splits, self.goal_level = self.expected_success(expected_success_effort)
        elif all_levels and const_splits and max_level:
            self.levels = all_levels
            self.splits = const_splits
            self.goal_level = max_level
        else:
            raise SamplerError("Non-default arg issue; use expected success or provide params")

    def __str__(self):
        return "Fixed Effort SMC sampler [model={}]".format(self.model_name)

    def restart_simulator_from_actions(self, simulator, actions):
        state, _, _ = simulator.restart()
        trace = [state]
        for action in actions:
            state, _, _ = simulator.step(action)
            trace.append(state)
        return state, trace

    def expected_success(self, user_effort):
        import src.smc.sampler.splitting.expected_success_method
        es = src.smc.sampler.splitting.expected_success_method.ExpectedSuccess(
            self.model_name, self.program, self.phi, self.trace_len,
            self.goal_deq, self.importance, user_effort)
        imp_to_level, splits, max_level = es.get_levels_splits()
        return imp_to_level, splits, max_level

    def make_program_simulator(self):
        simulator = stormpy.simulator.create_simulator(self.program)
        simulator.set_action_mode(stormpy.simulator.SimulatorActionMode.GLOBAL_NAMES)
        simulator.set_observation_mode(stormpy.simulator.SimulatorObservationMode.PROGRAM_LEVEL)
        return simulator