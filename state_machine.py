"""
A simple state machine implementation
"""

import logging
from shared import setup_logging

logger = setup_logging(logging.INFO, __name__)

class StateMachine:
    def __init__(self, initial_state):
        self.state = initial_state
        self.rules = {}

    def add_rule(self, from_state, to_state):
        if from_state not in self.rules:
            self.rules[from_state] = []
        self.rules[from_state].append(to_state)

    def can_transition(self, to_state):
        if self.state in self.rules and to_state in self.rules[self.state]:
            return True
        return False

    def transition(self, to_state):
        if self.can_transition(to_state):
            self.state = to_state
            logger.info(f"Transitioned to {self.state}")
        else:
            logger.warning(f"Cannot transition from {self.state} to {to_state}")

    def list_valid_transitions(self):
        if self.state in self.rules:
            return self.rules[self.state]
        return []

    def get_state(self):
        return self.state