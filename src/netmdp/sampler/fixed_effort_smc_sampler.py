from itertools import cycle

import numpy as np
from stormpy import PrismProgram

from src.netmdp.sampler.splitting.importance_function import ImportanceFunction
from src.netmdp.sampler.splitting.trace_snapshot import TraceSnapshot
from src.netmdp.sampler.splitting_smc_sampler import SplittingSMCSampler


class FixedEffortSMCSampler(SplittingSMCSampler):
    def __init__(self, model_name: str, program: PrismProgram, phi: str, trace_len: int,
                 goal_deq: int,
                 importance: ImportanceFunction,
                 user_effort: int,
                 expected_success_effort = None,
                 all_levels = None,
                 const_splits = None,
                 max_level = None):
        super().__init__(model_name, program, phi, trace_len, goal_deq, importance, expected_success_effort,
                         all_levels, const_splits, max_level)
        if max_level is None:
            self.splits = [s * user_effort for s in self.splits]
        if not self.splits:
            self.splits = [user_effort]

    def __str__(self):
        return "Fixed Effort SMC sampler [model={}]".format(self.model_name)

    def run(self):
        simulator = self.make_program_simulator()
        s = np.zeros(len(self.splits))

        t = 0
        state, _, _ = simulator.restart()
        level_start_points = [TraceSnapshot(t, [])]
        next_level_start_points = []
        imp = self.importance.get_importance(state, 0)

        unique_levels = list(dict.fromkeys(self.levels))
        # if len(unique_levels) > 1:
        #     imp1 = self.importance.get_importance(state, imp)
        for l_idx, l in enumerate(unique_levels):
            lsp_cycle = cycle(level_start_points)
            for i in range(self.splits[l_idx]):
                t, actions = next(lsp_cycle).untuple()
                state, trace = self.restart_simulator_from_actions(simulator, actions)
                imp = self.importance.get_importance(state, imp)
                while t < self.trace_len and self.levels[imp] <= l:
                    t += 1
                    state, _, _, action = self.step_simulator_weibull_traffic(simulator)
                    imp = self.importance.get_importance(state, imp)
                    trace.append(state)
                    actions.append(action)
                    if l == self.goal_level:
                        # print([f"(s={state["s"]}, d={state["d"]})" for state in trace])
                        if int(state["iq5_deqs_bl"]) == self.goal_deq:
                        # if self.trace_sat_property(f"trace_lte_{t}", trace, t):
                            s[l_idx] += 1
                            break
                    elif self.levels[imp] > l:
                        # print([f"(s={state["s"]}, d={state["d"]})" for state in trace])
                        # print([f"(deqs={state["iq5_deqs_bl"]})" for state in trace])
                        s[l_idx] += 1
                        if all([ts.get_actions() != actions for ts in next_level_start_points]):
                            next_level_start_points.append(TraceSnapshot(t, actions))
                            break
            if s[l_idx] == 0:
                return 0, s # no traces reached the next level
            level_start_points = next_level_start_points
            next_level_start_points = []
        p_hat = 1.0
        for l in range(len(self.splits)):
            p_hat *= s[l] / self.splits[l]
        # print(f"p_hat: {p_hat:.6f}")
        return p_hat, s

    def get_success_vector(self):
        _, s = self.run()
        return s

    def sample(self) -> float:
        p_hat, _ = self.run()
        # print("p_hat={}".format(p_hat))
        return p_hat