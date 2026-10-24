"""Settlement: who gets the pot.

Fold: the other player takes the whole pot. Showdown: the pot is split into side pots by
contribution level (with two players that just returns any uncalled excess); each pot goes
to the best hand among the players who paid into it (split on ties, or by the scorer's
shares for hi-lo / several boards). Every player then learns the opponent's cards
(showdown events) and their own chip result (end events).
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


def side_pots(total: list[int], live: list[int]) -> list[tuple[int, list[int]]]:
    """Split contributions into (amount, eligible players) pots. `live` = players still in
    the hand; folded players' chips stay in the pots they reached but can't win them.
    A pot only one live player paid into is that player's uncalled excess."""
    levels = sorted({total[p] for p in live})
    pots, prev = [], 0
    for lv in levels:
        amount = sum(min(t, lv) - min(t, prev) for t in total)
        eligible = [p for p in live if total[p] >= lv]
        if amount:
            pots.append((amount, eligible))
        prev = lv
    # Chips above the highest live level (from folded players) go to the last pot.
    extra = sum(max(0, t - prev) for t in total)
    if extra and pots:
        pots[-1] = (pots[-1][0] + extra, pots[-1][1])
    return pots


def settle(st, scorer) -> None:
    """Pay out `st` with a Scorer (or any object with evaluate(hole, board)). Sets st.deltas."""
    n = st.n_players
    if st.folded is not None:
        winners = [p for p in range(n) if p != st.folded]
        st.stack[winners[0]] += st.pot
    else:
        live = list(range(n))
        shares_all = None
        for amount, eligible in side_pots(st.total, live):
            if len(eligible) == 1:
                st.stack[eligible[0]] += amount         # uncalled excess back
                continue
            if shares_all is None:
                shares_all = showdown_shares(st, scorer)
            sub = [shares_all[p] if p in eligible else 0.0 for p in range(n)]
            norm = sum(sub)
            sub = [x / norm for x in sub] if norm > 0 else [1.0 / len(eligible) if p in eligible
                                                            else 0.0 for p in range(n)]
            chips = split_pot(amount, sub)
            for p in range(n):
                st.stack[p] += chips[p]
        st.showdown = True
        for p, cards in st.extra.get("reveal_later", {}).items():   # "revealed later" cards
            st.emit("reveal", p, visible=-1, cards=tuple(cards), what="later")
        for p in range(n):
            for q in range(n):
                if q != p:
                    st.emit("showdown", q, visible=p, cards=tuple(st.hole[q]))
    st.deltas = [st.stack[p] - st.start[p] for p in range(n)]
    for p in range(n):
        st.emit("end", p, visible=p, delta=st.deltas[p])
    st.done = True
