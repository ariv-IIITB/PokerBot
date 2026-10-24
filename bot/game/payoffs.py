"""Settlement: who gets the pot.

Fold: the other player takes the whole pot. Showdown: any uncalled excess (an all-in for
less than the other's bet) goes back first, then the matched pot goes to the best hand
(split on a tie). Every player then learns the opponent's cards (showdown events) and
their own chip result (end events).
"""
from __future__ import annotations

from bot.game.scoring import split_pot


def showdown_shares(st, scorer) -> list[float]:
    """Each player's fraction of the matched pot at showdown."""
    n = st.n_players
    if hasattr(scorer, "shares"):
        return scorer.shares([st.hole[p] for p in range(n)], [st.board])
    values = [scorer.evaluate(st.hole[p], st.board) for p in range(n)]
    best = max(values)
    winners = [p for p in range(n) if values[p] == best]
    return [1.0 / len(winners) if p in winners else 0.0 for p in range(n)]


def settle(st, scorer) -> None:
    """Pay out `st` with a Scorer (or any object with evaluate(hole, board)). Sets st.deltas."""
    n = st.n_players
    if st.folded is not None:
        winners = [p for p in range(n) if p != st.folded]
        st.stack[winners[0]] += st.pot
    else:
        matched = min(st.total)
        for p in range(n):
            st.stack[p] += st.total[p] - matched       # uncalled excess back
        chips = split_pot(matched * n, showdown_shares(st, scorer))
        for p in range(n):
            st.stack[p] += chips[p]
        st.showdown = True
        for p in range(n):
            for q in range(n):
                if q != p:
                    st.emit("showdown", q, visible=p, cards=tuple(st.hole[q]))
    st.deltas = [st.stack[p] - st.start[p] for p in range(n)]
    for p in range(n):
        st.emit("end", p, visible=p, delta=st.deltas[p])
    st.done = True
