"""Settlement: who gets the pot.

Fold: the other player takes the whole pot. Showdown: any uncalled excess (an all-in for
less than the other's bet) goes back first, then the matched pot goes to the best hand
(split on a tie). Every player then learns the opponent's cards (showdown events) and
their own chip result (end events).
"""
from __future__ import annotations


def settle(st, evaluate) -> None:
    """Pay out `st` using evaluate(hole, board) -> comparable value. Sets st.deltas."""
    n = st.n_players
    if st.folded is not None:
        winners = [p for p in range(n) if p != st.folded]
        st.stack[winners[0]] += st.pot
    else:
        matched = min(st.total)
        for p in range(n):
            st.stack[p] += st.total[p] - matched       # uncalled excess back
        values = [evaluate(st.hole[p], st.board) for p in range(n)]
        best = max(values)
        winners = [p for p in range(n) if values[p] == best]
        share = matched * n
        each, odd = divmod(share, len(winners))
        for i, p in enumerate(winners):
            st.stack[p] += each + (1 if i < odd else 0)
        st.showdown = True
        for p in range(n):
            for q in range(n):
                if q != p:
                    st.emit("showdown", q, visible=p, cards=tuple(st.hole[q]))
    st.deltas = [st.stack[p] - st.start[p] for p in range(n)]
    for p in range(n):
        st.emit("end", p, visible=p, delta=st.deltas[p])
    st.done = True
