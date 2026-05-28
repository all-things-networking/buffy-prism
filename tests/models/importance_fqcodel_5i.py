from stormpy import PrismProgram

from src.netmdp.sampler.sampler import SamplerError
from src.netmdp.sampler.splitting.importance_function import ImportanceFunction


class ImportanceFQCodel(ImportanceFunction):
    def __init__(self, program: PrismProgram, phi: str, trace_len: int, T: int, mult: int):
        super().__init__(program, phi, trace_len)
        # self.variables = dict()
        # for m in program.modules:
        #     for v in m.integer_variables:
        #         self.variables[v.name] = v.expression_variable.get_expression()
        #     for v in m.boolean_variables:
        #         self.variables[v.name] = v.expression_variable.get_expression()
        self.T = T
        self.mult = mult
        self.max_deqs = self.mult * (self.T // 5) + 1

    def get_all_levels(self):
        return list(range(self.max_deqs+1))

    def get_importance(self, state, prev_importance) -> int:
        deqs = int(state["iq5_deqs_bl"])
        if deqs < 0 or deqs > self.T:
            raise SamplerError(f"Invalid state iq5_deqs_bl={deqs}")
        return min(deqs, self.max_deqs)