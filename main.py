from lcrl.train import train
from lcrl.automata.minecraft_1 import minecraft_1
from lcrl.environments.minecraft import minecraft

# Tests LCRL library example
def train_minecraft_1():
    LDBA = minecraft_1
    MDP = minecraft

    # train the agent
    task = train(MDP, LDBA,
                  algorithm='ql',
                  episode_num=500,
                  iteration_num_max=4000,
                  discount_factor=0.95,
                  learning_rate=0.9
                  )

    print("Done!")

# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    train_minecraft_1()
