from stormpy import PrismProgram

from src.netmdp.sampler.sampler import SamplerError
from src.netmdp.sampler.splitting.importance_function import ImportanceFunction


class ImportanceDie(ImportanceFunction):
    def __init__(self, program: PrismProgram, phi: str, trace_len: int):
        super().__init__(program, phi, trace_len)
        # self.variables = dict()
        # for m in program.modules:
        #     for v in m.integer_variables:
        #         self.variables[v.name] = v.expression_variable.get_expression()
        #     for v in m.boolean_variables:
        #         self.variables[v.name] = v.expression_variable.get_expression()
        self.state_to_importance = [[0, 1, 0, 1, 2, 0, 0, 0], # d = 0
                                    [0, 1, 0, 1, 2, 0, 0, 0], # d = 1
                                    [0, 1, 0, 1, 2, 0, 0, 2], # d = 2
                                    [0, 1, 0, 1, 2, 0, 0, 0], # d = 3
                                    [0, 1, 0, 1, 2, 0, 0, 0], # d = 4
                                    [0, 1, 0, 1, 2, 0, 0, 0], # d = 5
                                    [0, 1, 0, 1, 2, 0, 0, 0]] # d = 6

    def get_all_levels(self):
        return [0,1,2]

    def get_importance(self, state, prev_importance) -> int:
        s = int(state["s"])
        d = int(state["d"])
        if s < 0 or s > 7:
            raise SamplerError(f"Invalid state s={s}")
        if d < 0 or d > 6:
            raise SamplerError(f"Invalid state d={d}")
        return self.state_to_importance[d][s]


class ImportanceDieOneRedundant(ImportanceFunction):
    def __init__(self, program: PrismProgram, phi: str, trace_len: int):
        super().__init__(program, phi, trace_len)
        # self.variables = dict()
        # for m in program.modules:
        #     for v in m.integer_variables:
        #         self.variables[v.name] = v.expression_variable.get_expression()
        #     for v in m.boolean_variables:
        #         self.variables[v.name] = v.expression_variable.get_expression()
        self.state_to_importance = [[0, 1, 0, 2, 1, 0, 0, 0], # d = 0
                                    [0, 1, 0, 2, 1, 0, 0, 3], # d = 1
                                    [0, 1, 0, 2, 1, 0, 0, 0], # d = 2
                                    [0, 1, 0, 2, 1, 0, 0, 0], # d = 3
                                    [0, 1, 0, 2, 1, 0, 0, 0], # d = 4
                                    [0, 1, 0, 2, 1, 0, 0, 0], # d = 5
                                    [0, 1, 0, 2, 1, 0, 0, 0]] # d = 6

    def get_all_levels(self):
        return [0,1,2,3]

    def get_importance(self, state, prev_importance) -> int:
        s = int(state["s"])
        d = int(state["d"])
        if s < 0 or s > 7:
            raise SamplerError(f"Invalid state s={s}")
        if d < 0 or d > 6:
            raise SamplerError(f"Invalid state d={d}")
        return self.state_to_importance[d][s]