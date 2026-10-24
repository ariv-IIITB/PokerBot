"""Settlement: who gets the pot, plus side payments.

Order at the end of a hand:
  1. Pot. Fold: the other player takes it. Showdown: side pots by contribution level (with
     two players this just returns an uncalled excess); each contested pot is split by the
     scorer's shares (ties, hi-lo, several boards), averaged over the runs when the board is
     "run it k times" after an all-in.
  2. Rake (payoff modifier): a percentage of the pot, capped, goes to the house. By default
     no rake when the hand ends before any board card is dealt ("no flop, no drop").
  3. Showdown side payments, each paid by the loser out of their remaining stack (capped):
       multiplier  an outright winner gets (factor - 1) x the loser's contribution again
       bounty      an outright winner holding a hole card of their bounty rank gets
                   bonus + (multiplier - 1) x the loser's contribution
  4. Side market (if a market step traded): settled on the final board.
Chips that leave the table (rake, burned bids) are counted in st.house, so
sum(deltas) + house == 0 always.
"""
from __future__ import annotations

from bot.game.scoring import _winners, hand_value, split_pot
from bot.game.state import ALL


def boards_of(st) -> list[list[int]]:
    """Every board's full card list (shared cards + that board's own cards)."""
    return [st.board + b for b in st.boards] if st.boards else [list(st.board)]


def showdown_shares(st, scorer, board_sets=None) -> list[float]:
    """Each player's fraction of a contested pot, averaged over runs (board sets)."""
    n = st.n_players
    board_sets = board_sets or [boards_of(st)]
    holes = [st.hole[p] for p in range(n)]
    total = [0.0] * n
    for boards in board_sets:
        if hasattr(scorer, "shares"):
            sh = scorer.shares(holes, boards)
        else:
            sh = [0.0] * n
            for board in boards:
                values = [hand_value(scorer, holes[p], board) for p in range(n)]
                win = _winners(values)
                for p in win:
                    sh[p] += 1.0 / len(win) / len(boards)
        for p in range(n):
            total[p] += sh[p] / len(board_sets)
    return total


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


def extra_runs(st, runs: int) -> list[list[list[int]]]:
    """Board sets for each run. Run 1 is the real board; runs 2..k re-deal every board card
    dealt after the all-in that closed the action (st.extra["allin_cut"])."""
    first = boards_of(st)
    cut = st.extra.get("allin_cut")
    if runs <= 1 or cut is None:
        return [first]
    shared_cut, own_cut = cut
    out = [first]
    for r in range(1, runs):
        n_shared = len(st.board) - shared_cut
        shared = st.board[:shared_cut] + st.deal(n_shared)
        own = []
        for i, b in enumerate(st.boards):
            keep = own_cut[i] if i < len(own_cut) else 0
            own.append(b[:keep] + st.deal(len(b) - keep))
        boards = [shared + b for b in own] if st.boards else [shared]
        new_cards = shared[shared_cut:] + [c for i, b in enumerate(own)
                                           for c in b[(own_cut[i] if i < len(own_cut) else 0):]]
        st.muck += new_cards
        for i, board in enumerate(boards):
            st.emit("run", visible=ALL, cards=tuple(board), value=r, board=i)
        out.append(boards)
    return out


def _rake(st, mods) -> None:
    for m in mods:
        if m.get("type") != "rake":
            continue
        if m.get("no_flop_no_drop", True) and not st.board and not st.boards:
            continue
        amount = min(int(st.pot * m.get("percent", 5) / 100), m.get("cap", 10**9))
        # Take the rake out of the winners' collections (before side payments).
        winners = sorted(range(st.n_players), key=lambda p: st.stack[p] - st.start[p],
                         reverse=True)
        left = amount
        for p in winners:
            take = min(left, max(0, st.stack[p]))
            st.stack[p] -= take
            left -= take
        st.house += amount - left


def _transfer(st, payer: int, payee: int, amount: int) -> int:
    amount = max(0, min(int(amount), st.stack[payer]))
    st.stack[payer] -= amount
    st.stack[payee] += amount
    return amount


def _showdown_bonuses(st, mods, outright_winner) -> None:
    if outright_winner is None:
        return
    w, loser = outright_winner, 1 - outright_winner
    for m in mods:
        if m.get("type") == "multiplier":
            extra = (float(m.get("factor", 1.0)) - 1.0) * st.total[loser]
            paid = _transfer(st, loser, w, extra)
            if paid:
                st.emit("payment", w, visible=ALL, value=paid, what="multiplier")
    bounty = st.extra.get("bounty")
    if bounty:
        rank = bounty["ranks"].get(w)
        if rank is not None and any(c % 64 < 52 and (c % 64) // 4 == rank for c in st.hole[w]):
            extra = bounty["bonus"] + (bounty["multiplier"] - 1.0) * st.total[loser]
            paid = _transfer(st, loser, w, extra)
            st.emit("payment", w, visible=ALL, value=paid, what="bounty")


def _settle_market(st) -> None:
    trade = st.extra.get("market")
    if not trade:
        return
    board = list(st.board) + (st.boards[0] if st.boards else [])
    need = max(0, st.rules.board_cards - len(board))
    if need:                                   # hand ended early: complete the board
        more = st.deal(min(need, len(st.deck)))
        st.muck += more
        board += more
        st.emit("reveal", -1, visible=ALL, cards=tuple(more), what="market")
    value = market_value(trade["quantity"], board)
    amount = round(trade["size"] * trade["scale"] * (value - trade["price"]))
    buyer, seller = trade["buyer"], trade["seller"]
    paid = _transfer(st, seller, buyer, amount) if amount > 0 else -_transfer(st, buyer, seller, -amount)
    st.emit("market", -1, visible=ALL, value=value, paid=paid)


def market_value(quantity: str, board) -> int:
    """The quantities a side market can trade on, computed from a final board."""
    faces = [c % 64 for c in board if c % 64 < 52]
    if quantity == "board_rank_sum":
        return sum(f // 4 + 2 for f in faces)
    if quantity == "board_hearts":
        return sum(1 for f in faces if f % 4 == 2)
    if quantity == "board_high":
        return max((f // 4 + 2 for f in faces), default=0)
    raise ValueError(f"unknown market quantity {quantity!r}")


def market_range(quantity: str, n_cards: int) -> tuple[int, int]:
    if quantity == "board_rank_sum":
        return 2 * n_cards, 14 * n_cards
    if quantity == "board_hearts":
        return 0, n_cards
    if quantity == "board_high":
        return 2, 14
    raise ValueError(f"unknown market quantity {quantity!r}")


def settle(st, scorer, runs: int = 1, modifiers=()) -> None:
    """Pay out `st` with a Scorer (or any object with evaluate(hole, board)). Sets st.deltas."""
    n = st.n_players
    mods = list(modifiers)
    outright = None
    if st.folded is not None:
        winners = [p for p in range(n) if p != st.folded]
        st.stack[winners[0]] += st.pot
    else:
        board_sets = extra_runs(st, runs)
        live = list(range(n))
        shares_all = None
        for amount, eligible in side_pots(st.total, live):
            if len(eligible) == 1:
                st.stack[eligible[0]] += amount         # uncalled excess back
                continue
            if shares_all is None:
                shares_all = showdown_shares(st, scorer, board_sets)
            sub = [shares_all[p] if p in eligible else 0.0 for p in range(n)]
            norm = sum(sub)
            sub = [x / norm for x in sub] if norm > 0 else [1.0 / len(eligible) if p in eligible
                                                            else 0.0 for p in range(n)]
            chips = split_pot(amount, sub)
            for p in range(n):
                st.stack[p] += chips[p]
        st.showdown = True
        if shares_all is not None:
            full = [p for p in range(n) if shares_all[p] >= 1.0 - 1e-9]
            outright = full[0] if full else None
        for p, cards in st.extra.get("reveal_later", {}).items():   # "revealed later" cards
            st.emit("reveal", p, visible=ALL, cards=tuple(cards), what="later")
        for p in range(n):
            for q in range(n):
                if q != p:
                    st.emit("showdown", q, visible=p, cards=tuple(st.hole[q]))
        bounty = st.extra.get("bounty")
        if bounty and bounty.get("hidden"):                          # chosen bounties shown
            for p, rank in bounty["ranks"].items():
                st.emit("bounty", p, visible=ALL, value=rank, cards=())
    _rake(st, mods)
    if st.showdown:
        _showdown_bonuses(st, mods, outright)
    _settle_market(st)
    st.deltas = [st.stack[p] - st.start[p] for p in range(n)]
    for p in range(n):
        st.emit("end", p, visible=p, delta=st.deltas[p])
    st.done = True
