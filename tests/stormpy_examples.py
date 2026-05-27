import random

import stormpy
import stormpy.examples
import stormpy.examples.files
import stormpy.simulator


path = stormpy.examples.files.prism_mdp_slipgrid
prism_program = stormpy.parse_prism_program(path)

simulator = stormpy.simulator.create_simulator(prism_program, seed=42)

# 3 paths of at most 20 steps.
paths = []
for m in range(3):
    path = []
    state, reward, labels = simulator.restart()
    path = [f"({state['x']},{state['y']})"]
    for n in range(30):
        actions = simulator.available_actions()
        select_action = random.randint(0, len(actions) - 1)
        path.append(f"--{actions[select_action]}-->")
        state, reward, labels = simulator.step(actions[select_action])
        path.append(f"({state['x']},{state['y']})")
        if labels:
            path.append(f"({labels})")
        if simulator.is_done():
            break
    paths.append(path)
for path in paths:
    print(" ".join(path))