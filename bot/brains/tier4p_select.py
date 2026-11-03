"""Member selection for tier4p in "auto" mode (PC fills this in; PA ships a stub).

`choose_member(brain, street)` returns one of tier4p.MEMBER_NAMES. The stub always plays "base",
so "auto" is Tier 3 until PC replaces this file. It must not edit tier4p.py.
"""
from __future__ import annotations


def choose_member(brain, street: int) -> str:
    return "base"
