"""
TCP Socket Runner for Heads-Up Pokerbot competition engines.
Compatible with standard MIT Pokerbots line-based protocol.
"""

import sys
import socket
from skeleton.actions import FoldAction, CallAction, CheckAction, RaiseAction
from skeleton.states import (
    GameState,
    TerminalState,
    RoundState,
    STARTING_STACK,
    BIG_BLIND,
    SMALL_BLIND,
)


def parse_action(line):
    """Parses an action string received from the engine."""
    parts = line.split()
    act = parts[0]
    if act == "F":
        return FoldAction()
    elif act == "C":
        return CallAction()
    elif act == "K":
        return CheckAction()
    elif act == "R":
        return RaiseAction(int(parts[1]))
    return CheckAction()


def action_to_str(action):
    """Encodes an action into the tournament protocol string."""
    if isinstance(action, FoldAction):
        return "F"
    elif isinstance(action, CallAction):
        return "C"
    elif isinstance(action, CheckAction):
        return "K"
    elif isinstance(action, RaiseAction):
        return f"R {int(action.amount)}"
    return "K"


def run_socket(bot, host, port):
    """
    Connects to the competition engine via TCP socket and drives the bot.
    Handles all network I/O, state construction, and exception guarding.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))
    socket_file = sock.makefile("r")

    active = 0
    round_state = None
    game_state = GameState(0, 60.0, 1)

    while True:
        line = socket_file.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        cmd = parts[0]

        if cmd == "T":
            # Time update: T <game_clock>
            clock = float(parts[1])
            game_state = GameState(game_state.bankroll, clock, game_state.round_num)

        elif cmd == "P":
            # Active seat assignment: P <active>
            active = int(parts[1])

        elif cmd == "H":
            # Hole cards dealt: H <card1> <card2>
            cards = parts[1:3]
            # Initialize round state
            # Button is 0 if active == 0 and button == 0, etc.
            round_state = RoundState(
                button=0,
                street=0,
                pips=[SMALL_BLIND, BIG_BLIND],
                stacks=[STARTING_STACK - SMALL_BLIND, STARTING_STACK - BIG_BLIND],
                hands=[cards if active == 0 else None, cards if active == 1 else None],
                deck=[],
                previous_state=None,
            )
            try:
                bot.handle_new_round(game_state, round_state, active)
            except Exception as e:
                # Tournament safety: never crash
                pass

        elif cmd == "B":
            # Board cards update: B <card1> ...
            board = parts[1:]
            street = len(board)
            if round_state is not None:
                round_state = RoundState(
                    button=round_state.button,
                    street=street,
                    pips=[0, 0],
                    stacks=round_state.stacks,
                    hands=round_state.hands,
                    deck=board,
                    previous_state=round_state,
                )

        elif cmd == "G":
            # Game state update: G <bankroll> <clock> <round_num>
            bankroll = int(parts[1])
            clock = float(parts[2])
            round_num = int(parts[3])
            game_state = GameState(bankroll, clock, round_num)

        elif cmd == "D":
            # Round over / deltas: D <delta_0> <delta_1>
            d0, d1 = int(parts[1]), int(parts[2])
            term = TerminalState([d0, d1], round_state)
            try:
                bot.handle_round_over(game_state, term, active)
            except Exception:
                pass

        elif cmd == "A":
            # Action request from engine
            try:
                action = bot.get_action(game_state, round_state, active)
            except Exception:
                # Emergency safe action
                legal = round_state.legal_actions() if round_state else {CheckAction}
                action = CheckAction() if CheckAction in legal else (CallAction() if CallAction in legal else FoldAction())

            sock.sendall((action_to_str(action) + "\n").encode())

        elif cmd == "Q":
            # Quit
            break

    sock.close()
