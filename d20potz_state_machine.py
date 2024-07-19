"""
This module contains the state machine for the D20 Potz project.
"""

import logging
from enum import Enum
from shared import setup_logging
from state_machine import StateMachine

logger = setup_logging(logging.INFO, __name__)


class PotzState(Enum):
    root = "root"
    stress = "stress"
    harm = "harm"
    timer = "timer"
    roll = "roll"


class PotzStateMachine(StateMachine):
    def __init__(self, initial_state):
        if initial_state not in PotzState:
            raise ValueError(f"Invalid initial state {initial_state}")
        super().__init__(initial_state)
        self.add_fixed_rules()

    def add_fixed_rules(self):
        self.add_rule(PotzState.root, PotzState.stress)
        self.add_rule(PotzState.root, PotzState.harm)
        self.add_rule(PotzState.root, PotzState.timer)
        self.add_rule(PotzState.root, PotzState.roll)
        self.add_rule(PotzState.stress, PotzState.root)
        self.add_rule(PotzState.harm, PotzState.root)
        self.add_rule(PotzState.timer, PotzState.root)
        self.add_rule(PotzState.roll, PotzState.root)
