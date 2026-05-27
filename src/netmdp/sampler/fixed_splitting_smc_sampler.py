from collections import deque

from stormpy import PrismProgram

from src.netmdp.sampler.splitting.importance_function import ImportanceFunction
from src.netmdp.sampler.splitting.trace_snapshot import LevelTraceSnapshot
from src.netmdp.sampler.splitting_smc_sampler import SplittingSMCSampler


class FixedSplittingSMCSampler(SplittingSMCSampler):
    def __init__(self, model_name: str, program: PrismProgram, phi: str, trace_len: int,
                 goal_deq: int,
                 importance: ImportanceFunction,
                 expected_success_effort = None,
                 all_levels = None,
                 const_splits = None,
                 max_level = None):
        super().__init__(model_name, program, phi, trace_len, goal_deq, importance, expected_success_effort,
                         all_levels, const_splits, max_level)
        self.goal_likelihood = self.compute_goal_likelihood()

    def __str__(self):
        return "Fixed Splitting SMC sampler [model={}]".format(self.model_name)

    def compute_goal_likelihood(self):
        level_cond_prob = 1.0
        for l in range(len(self.splits)):
            level_cond_prob *= self.splits[l]
        return 1.0 / level_cond_prob

    def sample(self) -> float:
        simulator = self.make_program_simulator()
        p_hat = 0

        level_to_split_idx = dict()
        idx = 0
        for l in self.levels:
            if l not in level_to_split_idx.keys():
                level_to_split_idx[l] = idx
                idx += 1

        t = 0
        state, _, _ = simulator.restart()
        trace_queue = deque()
        for i in range(self.splits[level_to_split_idx[self.levels[0]]]):
            trace_queue.append(LevelTraceSnapshot(t, [], self.levels[0]))
        # trace_queue.append(LevelTraceSnapshot(t, [], self.levels[0]))
        imp = self.importance.get_importance(state, 0)

        while trace_queue: # is not empty
            t, actions, level = trace_queue.popleft().untuple()
            state, trace = self.restart_simulator_from_actions(simulator, actions)
            imp = self.importance.get_importance(state, imp)
            start_level = level
            while t < self.trace_len and self.levels[imp] >= start_level:
                t += 1
                state, _, _, action = self.step_simulator_weibull_traffic(simulator)
                imp = self.importance.get_importance(state, imp)
                trace.append(state)
                actions.append(action)
                if level == self.goal_level:
                    if int(state["iq5_deqs_bl"]) == self.goal_deq:
                    # if self.trace_sat_property(f"trace_lte_{t}", trace, t):
                        p_hat += self.goal_likelihood
                        break
                elif self.levels[imp] > level:
                    level = self.levels[imp]
                    for i in range(self.splits[level_to_split_idx[level]]-1):
                        # print([f"appended x{self.splits[level_to_split_idx[level]]}: "] + [f"(s={state["s"]}, d={state["d"]})" for state in trace])
                        trace_queue.append(LevelTraceSnapshot(t, actions, level))
            # print([f"p_hat: {p_hat}"] + [f"(s={state["s"]}, d={state["d"]})" for state in trace])
        return p_hat