import random

import stormpy
from stormpy import PrismProgram
from stormpy.simulator import Simulator

from src.netmdp.sampler.base_smc_sampler import BaseSMCSampler
from src.netmdp.sampler.sampler import SamplerError


class BaseSymbolicSMCSampler(BaseSMCSampler):
    def __init__(self, model_name: str, program: PrismProgram, phi: str, trace_len: int, goal_deq: int):
        super().__init__(model_name, program, phi, trace_len)
        self.goal_deq = goal_deq

    def __str__(self):
        return "Base (Symbolic) SMC sampler [model={}]".format(self.model_name)

    def step_simulator_unif(self, simulator):
        actions = simulator.available_actions()
        select_action = random.randint(0, len(actions) - 1)
        state, reward, labels = simulator.step(actions[select_action])
        return state, reward, labels, actions[select_action]

    def step_simulator_weibull_traffic(self, simulator):
        actions = simulator.available_actions()
        if len(actions) == 1:
            select_action = actions[0]
        else:
            if len(actions) != 5:
                raise SamplerError(f"unexpected number of actions: {actions}")
            # Choice index k is the k-th REC_PKT_GET_IQi command, i.e. k arrivals. The five commands share one
            # action label, so this must run in INDEX_LEVEL mode: in GLOBAL_NAMES mode step(label) always takes
            # the first matching choice (0 arrivals) and the traffic weights are silently ignored.
            select_action = random.choices(actions, weights=[0.4, 0.39, 0.14, 0.05, 0.02])[0]
        state, reward, labels = simulator.step(select_action)
        return state, reward, labels, select_action

    def make_program_simulator(self):
        simulator = stormpy.simulator.create_simulator(self.program)
        simulator.set_action_mode(stormpy.simulator.SimulatorActionMode.INDEX_LEVEL)
        simulator.set_observation_mode(stormpy.simulator.SimulatorObservationMode.PROGRAM_LEVEL)
        return simulator

    def sample(self) -> float:
        simulator = self.make_program_simulator()
        t = 0
        state, _, _ = simulator.restart()
        trace = [state]
        while t < self.trace_len:
            t += 1
            state, _, _, _ = self.step_simulator_weibull_traffic(simulator)
            trace.append(state)
        if int(state["iq5_deqs_bl"]) == self.goal_deq: #self.trace_sat_property(f"trace_lte_{t}", trace, t):
            return 1
        else:
            return 0