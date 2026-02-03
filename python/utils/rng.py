import random

class SeededRNG:
    def __init__(self, seed=None):
        if seed is None:
            seed = random.randint(0, 1000000)
        self.seed = seed
        self.rng = random.Random(seed)

    def reseed(self, seed):
        self.seed = seed
        self.rng = random.Random(seed)

    def get_seed(self):
        return self.seed

    def random(self):
        return self.rng.random()

    def randint(self, a, b):
        return self.rng.randint(a, b)

    def choice(self, seq):
        return self.rng.choice(seq)

    def weighted_choice(self, choices):
        """
        choices: [ (item, weight), ... ]
        """
        total = sum(w for i, w in choices)
        r = self.rng.uniform(0, total)
        upto = 0
        for item, weight in choices:
            if upto + weight >= r:
                return item
            upto += weight
        return choices[-1][0]
