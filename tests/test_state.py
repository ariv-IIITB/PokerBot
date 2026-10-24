from helpers import scripted_match

from bot.actions import Action
from bot.cards import parse_cards
from bot.protocol import parse_line
from bot.state import ME, OPP, GameState


def test_scripted_hand_tracking() -> None:
    st = GameState()
    lines = scripted_match(hands=2, timebank=30.0)
    # Feed MATCH + first hand up to (not including) END; act like the bot after each ACT.
    for line in lines[:11]:
        msg = parse_line(line)
        st.apply(msg)
        if line.startswith("ACT"):
            st.record_my_action(Action.call())

    assert st.match.hands == 2 and st.match.timebank == 30.0
    h = st.hand
    assert h is not None and h.hand_id == 0 and h.seat == 0
    assert h.hole == parse_cards("Ah,Kd")
    assert h.board == parse_cards("Ts,9h,2c") and h.street == 1
    assert (h.pot, h.tocall, h.my_stack, h.opp_stack) == (14, 10, 398, 388)
    assert h.opp_cards == parse_cards("Qs,Qd")
    assert h.actions_on(0) == [Action.call(), Action.check()]
    assert h.actions_on(1, OPP) == [Action.raise_to(10)]
    assert len(h.actions_on(1, ME)) == 3
    assert st.timeleft == 50.0
    assert st.hands_remaining == 2 and not h.finished

    st.apply(parse_line(lines[11]))  # END delta=-2
    assert h.finished and h.delta == -2
    assert st.hands_played == 1 and st.bankroll == -2 and st.hands_remaining == 1

    for line in lines[12:]:
        st.apply(parse_line(line))
    assert st.hands_played == 2 and st.bankroll == -4 and st.match_over
    assert st.hand.hand_id == 1


def test_duplicate_end_counted_once() -> None:
    st = GameState()
    for line in ["HAND id=1 seat=0 stack=400 oppstack=400", "END delta=5", "END delta=5"]:
        st.apply(parse_line(line))
    assert st.hands_played == 1 and st.bankroll == 5


def test_hand_messages_before_any_hand_ignored() -> None:
    st = GameState()
    st.apply(parse_line("HOLE cards=Ah,Kd"))
    st.apply(parse_line("END delta=5"))
    assert st.hand is None and st.hands_played == 0
