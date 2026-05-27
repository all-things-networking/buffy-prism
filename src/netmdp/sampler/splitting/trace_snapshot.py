from copy import copy


class TraceSnapshot:
    def __init__(self, time, actions):
        self.time = copy(time)
        self.actions = copy(actions)

    def __copy__(self):
        return TraceSnapshot(self.time, self.actions)

    def get_actions(self):
        return self.actions

    def untuple(self):
        return copy(self.time), copy(self.actions)

class LevelTraceSnapshot(TraceSnapshot):
    def __init__(self, time, actions, level):
        super().__init__(time, actions)
        self.level = copy(level)

    def untuple(self):
        return copy(self.time), copy(self.actions), copy(self.level)
