"""
Action types for Heads-Up No-Limit Texas Hold'em.
Uses namedtuples to match standard pokerbot competition specifications.
"""

from collections import namedtuple

FoldAction = namedtuple("FoldAction", [])
CallAction = namedtuple("CallAction", [])
CheckAction = namedtuple("CheckAction", [])
RaiseAction = namedtuple("RaiseAction", ["amount"])
