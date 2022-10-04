import random
from typing import Tuple, Union

from pycparser.c_ast import Node

from semtransforms.transformation import FindNodes


class Transformer:
    def __init__(self, *trans: Union[FindNodes, Tuple[FindNodes, object]],
                 transform_selector=random.choices,
                 config_selector=random.choice):
        self.trans = list(map(self.add_priority, trans))
        self.transform_selector = transform_selector
        self.config_selector = config_selector

    @staticmethod
    def add_priority(trans):
        """check/ add the existence of a probability"""
        if issubclass(trans.__class__, FindNodes):  # Node without probability, defaults to 1
            return trans, 1.
        if isinstance(trans, tuple) and len(trans) == 2 and issubclass(trans[0].__class__, FindNodes):
            if isinstance(trans[1], (int, float)):  # Node and probability value
                return trans[0], max(trans[1], 0.)
            if callable(trans[1]):                  # Node and probability function
                return trans
        raise ValueError(f"{trans} cannot be parsed to a Transform + Weight Tuple")

    def add(self, *trans):
        self.trans += list(map(self.add_priority, trans))

    @staticmethod
    def probability(possibility: Tuple, run: int) -> float:
        return max(0, possibility[1](run)) if callable(possibility[1]) else possibility[1]

    def transform(self, ast: Node, repetitions=1):
        """do any number of transformations on the ast with the given probabilities"""
        trace = ""
        for i in range(repetitions):
            # calculate probabilities where necessary and keep only those > 0
            possibilities = list(filter(lambda t: t[1] > 0, map(lambda t: (t[0], self.probability(t, i)), self.trans)))
            # find a random choice from possibilities with at least one possible configuration
            transforms = None
            while not transforms:
                if not possibilities:
                    return trace[:-1] if trace else ""
                choice = self.transform_selector(*zip(*possibilities))[0]
                transforms = choice.all_transforms(ast)
                possibilities = list(filter(lambda p: p[0] != choice, possibilities))

            # Loop is run at least run once because random_number >= 0, thus choice is always initialized
            # noinspection PyUnboundLocalVariable
            transform = self.config_selector(transforms)
            trace += f"{choice.func.__name__}: {transforms.index(transform)}\n"
            transform()
        return trace[:-1] if trace else ""