#!/usr/bin/env python3
"""Discard Hold'em bot: Monte Carlo equity against a uniformly random hand.

Design (deliberately simple):
  * Equity = P(win) + P(tie)/2 against a uniformly random opponent hand,
    estimated by vectorised Monte Carlo (numpy) inside a per-decision time budget.
  * Before the discard (preflop / flop betting) the opponent holds 3 random
    cards and both players are modelled as keeping their best two on the flop.
  * The discard is chosen by simulation: for each of our three possible keeps we
    play out the same random opponents and runouts and keep the best one.
  * Betting: call when equity beats pot odds plus a margin (the margin grows with
    the bet size); value bet / raise at fixed fractions of the pot when equity is
    high; never bluff; no opponent modelling.
  * Safety: every reply is validated against the legal actions, any exception
    falls back to a cheap safe action, and the per-decision compute budget is
    derived from time_left_ms so the time bank is never exhausted.

Protocol: JSON lines on stdin/stdout, stdout carries protocol messages only.
Only the standard library and numpy are used.
"""
import os

# One vCPU: keep BLAS/OpenMP from spawning threads (must be set before numpy).
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import json
import sys
import time
from itertools import combinations_with_replacement, permutations
from math import comb

import numpy as np

np.seterr(all="ignore")

# --------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------
RANKS = "23456789TJQKA"
SUITS = "shdc"


def c2i(s):
    """'As' -> int id (rank*4 + suit)."""
    return RANKS.index(s[0].upper()) * 4 + SUITS.index(s[1].lower())


def i2c(i):
    return RANKS[i >> 2] + SUITS[i & 3]


_SUIT_PERMS = list(permutations(range(4)))


def canon_key(hole):
    """Suit-isomorphism class of a 3-card hand, e.g. 'A0K0Q1' (rank char + relabelled suit)."""
    best = None
    for perm in _SUIT_PERMS:
        t = sorted((-(c >> 2), perm[c & 3]) for c in hole)
        if best is None or t < best:
            best = t
    return "".join(RANKS[-r] + str(s) for r, s in best)


# --------------------------------------------------------------------------
# Vectorised 5/6/7-card hand evaluator
#   score = category * 13^5 + kickers in base 13 (higher is better)
#   categories: 0 high card, 1 pair, 2 two pair, 3 trips, 4 straight,
#               5 flush, 6 full house, 7 quads, 8 straight flush
# --------------------------------------------------------------------------
AR13 = np.arange(13, dtype=np.int8)
AR13P1 = np.arange(1, 14, dtype=np.int8)
EYE13 = np.eye(13, dtype=np.int8)
EYE4 = np.eye(4, dtype=np.int8)
ONEHOT = np.zeros((14, 13), dtype=bool)  # row 13 (== index -1) is all False
ONEHOT[np.arange(13), np.arange(13)] = True
MULT = np.array([13 ** 4, 13 ** 3, 13 ** 2, 13, 1], dtype=np.int32)
CAT = 13 ** 5
AR10 = np.arange(10, dtype=np.int8)


def _top1(mask):
    """Highest rank index set in each row of mask, -1 if none."""
    return (np.where(mask, AR13P1, np.int8(0)).max(axis=1) - 1).astype(np.int8)


def _topk(mask, k):
    """k highest rank indices per row (descending), padded with -1."""
    v = np.where(mask, AR13, np.int8(-1))
    v.sort(axis=1)
    return v[:, ::-1][:, :k]


def _pack(cat, cols):
    ks = np.maximum(cols, 0).astype(np.int32)
    out = ks[:, 0] * MULT[0]
    for i in range(1, ks.shape[1]):
        out = out + ks[:, i] * MULT[i]
    return out + cat * CAT


def _straight_high(pres):
    """Top rank index of the best straight in each row of a (n,13) bool, else -1."""
    ext = np.concatenate([pres[:, 12:13], pres], axis=1)
    w = (ext[:, 0:10] & ext[:, 1:11] & ext[:, 2:12] & ext[:, 3:13] & ext[:, 4:14])
    idx = np.where(w, AR10, np.int8(-1)).max(axis=1)
    return np.where(idx >= 0, idx + 3, -1).astype(np.int8)


def _eval_slow(cards):
    """Direct evaluation. cards: (n, m) int array, 5 <= m <= 7. Returns (n,) int32."""
    cards = np.asarray(cards)
    ranks = cards >> 2
    suits = cards & 3
    oh = EYE13[ranks]  # (n, m, 13)
    counts = oh.sum(axis=1, dtype=np.int8)  # (n, 13)
    sc = EYE4[suits].sum(axis=1, dtype=np.int8)  # (n, 4)
    single = counts >= 1
    pm = counts >= 2

    # high card
    best = _pack(0, _topk(single, 5))

    # pair
    p1 = _top1(pm)
    kick3 = _topk(single & ~ONEHOT[p1], 3)
    cand = _pack(1, np.column_stack([p1, kick3]))
    best = np.where(p1 >= 0, cand, best)

    # two pair
    p2 = _top1(pm & ~ONEHOT[p1])
    k1 = _top1(single & ~ONEHOT[p1] & ~ONEHOT[p2])
    cand = _pack(2, np.column_stack([p1, p2, k1]))
    best = np.where(p2 >= 0, cand, best)

    # trips
    t = _top1(counts >= 3)
    kick2 = _topk(single & ~ONEHOT[t], 2)
    cand = _pack(3, np.column_stack([t, kick2]))
    best = np.where(t >= 0, cand, best)

    # straight
    sh = _straight_high(single)
    best = np.where(sh >= 0, _pack(4, sh[:, None]), best)

    # full house
    pp = _top1(pm & ~ONEHOT[t])
    cand = _pack(6, np.column_stack([t, pp]))
    best = np.where((t >= 0) & (pp >= 0), cand, best)

    # quads
    q = _top1(counts >= 4)
    k1 = _top1(single & ~ONEHOT[q])
    cand = _pack(7, np.column_stack([q, k1]))
    best = np.where(q >= 0, cand, best)

    # flush / straight flush (only rows that have 5+ cards of one suit)
    fidx = np.flatnonzero(sc.max(axis=1) >= 5)
    if fidx.size:
        fs = sc[fidx].argmax(axis=1)
        fm = (suits[fidx] == fs[:, None])[:, :, None]
        fp = (oh[fidx] * fm).sum(axis=1) > 0
        fscore = _pack(5, _topk(fp, 5))
        sfh = _straight_high(fp)
        sfscore = np.where(sfh >= 0, _pack(8, sfh[:, None]), -1)
        cur = best[fidx]
        # a flush beats straight/trips/two pair/pair, but not full house / quads
        cur = np.where((fscore > cur), fscore, cur)
        cur = np.where(sfscore > cur, sfscore, cur)
        best[fidx] = cur
    return best


# Fast path: for hands without a flush the score depends only on the multiset of
# ranks (50,388 multisets of 7 ranks), so it is a table lookup on the colex index of
# the sorted ranks. Tables are built once at start-up with the direct evaluator.
# Rows with 5+ cards of one suit go through the direct evaluator.
_TABLES = {}
_BIN = {}
_ARM = {}
AR4 = np.arange(4, dtype=np.int32)


def _build_table(m):
    combos = np.array(list(combinations_with_replacement(range(13), m)), dtype=np.int8)
    # give every card a suit so that no 5 share one (round robin keeps equal ranks apart)
    cards = combos * 4 + (np.arange(m, dtype=np.int8) & 3)
    scores = _eval_slow(cards)
    binom = np.zeros((m, 13 + m - 1), dtype=np.int64)
    for i in range(m):
        for sv in range(13 + m - 1):
            binom[i, sv] = comb(sv, i + 1)
    _BIN[m] = binom
    _ARM[m] = np.arange(m)
    idx = _multiset_index(combos, m)
    table = np.zeros(comb(12 + m, m), dtype=np.int32)
    table[idx] = scores
    _TABLES[m] = table


def _multiset_index(ranks, m):
    s = np.sort(ranks, axis=1).astype(np.intp) + _ARM[m]
    return _BIN[m][_ARM[m], s].sum(axis=1)


def build_tables():
    for m in (5, 7):
        if m not in _TABLES:
            _build_table(m)


def eval_cards(cards):
    """Score hands. cards: (n, m) int array, 5 <= m <= 7. Returns (n,) int32.
    score = category * 13^5 + kickers; larger is better; equal score = tie."""
    cards = np.asarray(cards)
    m = cards.shape[1]
    table = _TABLES.get(m)
    if table is None:
        return _eval_slow(cards)
    score = table[_multiset_index(cards >> 2, m)]
    packed = (np.int32(1) << ((cards & 3).astype(np.int32) << 2)).sum(axis=1)
    fl = (((packed & 15) >= 5) | (((packed >> 4) & 15) >= 5)
          | (((packed >> 8) & 15) >= 5) | (((packed >> 12) & 15) >= 5))
    fidx = np.flatnonzero(fl)
    if fidx.size:
        score[fidx] = _eval_slow(cards[fidx])
    return score


# --------------------------------------------------------------------------
# Sampling helpers
# --------------------------------------------------------------------------
KEEP = np.array([[1, 2], [0, 2], [0, 1]], dtype=np.intp)  # option j drops card j


def draw(pool, n, k, rng):
    """n independent draws of k distinct cards from pool (partial Fisher-Yates)."""
    p = pool.shape[0]
    perm = np.tile(pool, (n, 1))
    rows = np.arange(n)
    for i in range(k):
        j = i + (rng.random(n) * (p - i)).astype(np.intp)
        a = perm[rows, i]
        b = perm[rows, j]
        perm[rows, i] = b
        perm[rows, j] = a
    return perm[:, :k]


def make_pool(known):
    ks = set(int(x) for x in known)
    return np.array([c for c in range(52) if c not in ks], dtype=np.int8)


def heuristic_keep(h3, flop):
    """Modelled discard: keep the two cards that make the best 5-card flop hand.
    h3: (n,3) hole cards, flop: (n,3). Returns (n,2) kept cards."""
    n = h3.shape[0]
    opts = [np.concatenate([h3[:, KEEP[j]], flop], axis=1) for j in range(3)]
    sc = eval_cards(np.concatenate(opts, axis=0)).reshape(3, n)
    d = sc.argmax(axis=0)
    return np.take_along_axis(h3, KEEP[d], axis=1)


def _outcome(ms, os_):
    return (ms > os_).astype(np.float64) + 0.5 * (ms == os_)


# One "chunk" function per situation. Each returns per-option sums of outcomes.
def chunk_post(n, my2, board, pool, rng):
    """Both discards done: opponent holds 2 uniformly random unseen cards."""
    need_board = 5 - len(board)
    d = draw(pool, n, 2 + need_board, rng)
    opp2 = d[:, :2]
    parts = [np.broadcast_to(np.array(board, dtype=np.int8), (n, len(board)))]
    if need_board:
        parts.append(d[:, 2:])
    b5 = np.concatenate(parts, axis=1)
    my7 = np.concatenate([np.broadcast_to(np.array(my2, dtype=np.int8), (n, 2)), b5], axis=1)
    opp7 = np.concatenate([opp2, b5], axis=1)
    both = eval_cards(np.concatenate([my7, opp7], axis=0))
    return np.array([_outcome(both[:n], both[n:]).sum()])


def exact_river(my2, board, pool):
    """River with both discards known: enumerate every opponent holding."""
    a, b = np.triu_indices(pool.shape[0], 1)
    m = a.shape[0]
    opp2 = np.stack([pool[a], pool[b]], axis=1)
    bd = np.broadcast_to(np.array(board, dtype=np.int8), (m, 5))
    opp7 = np.concatenate([opp2, bd], axis=1)
    my7 = np.array([list(my2) + list(board)], dtype=np.int8)
    ms = eval_cards(my7)[0]
    os_ = eval_cards(opp7)
    return float(_outcome(np.full(m, ms), os_).mean())


def chunk_flop(n, my3, flop, pool, rng):
    """Flop known, discards pending: returns the win sum for each of our 3 keeps."""
    d = draw(pool, n, 5, rng)  # opp3 + turn + river
    opp3 = d[:, :3]
    flop_b = np.broadcast_to(np.array(flop, dtype=np.int8), (n, 3))
    b5 = np.concatenate([flop_b, d[:, 3:5]], axis=1)
    okeep = heuristic_keep(opp3, flop_b)
    os_ = eval_cards(np.concatenate([okeep, b5], axis=1))
    h = np.array(my3, dtype=np.int8)
    mine = np.concatenate(
        [np.concatenate([np.broadcast_to(h[KEEP[j]], (n, 2)), b5], axis=1) for j in range(3)], axis=0)
    ms = eval_cards(mine).reshape(3, n)
    w = (ms > os_[None, :]).astype(np.float64) + 0.5 * (ms == os_[None, :])
    return w.sum(axis=1)


def chunk_preflop(n, my3, pool, rng):
    """Nothing but our 3 cards known; both sides keep their best two on the flop."""
    d = draw(pool, n, 8, rng)  # opp3 + 5 board cards
    opp3 = d[:, :3]
    b5 = d[:, 3:8]
    flop = b5[:, :3]
    h3 = np.broadcast_to(np.array(my3, dtype=np.int8), (n, 3))
    okeep = heuristic_keep(opp3, flop)
    mkeep = heuristic_keep(h3, flop)
    both = eval_cards(np.concatenate(
        [np.concatenate([mkeep, b5], axis=1), np.concatenate([okeep, b5], axis=1)], axis=0))
    return np.array([_outcome(both[:n], both[n:]).sum()])


def run_chunks(fn, k, deadline, n0, max_total):
    """Call fn(n) repeatedly (n samples each) until the deadline. Returns (sums, total, sec/sample)."""
    acc = np.zeros(k)
    total = 0
    n = max(64, min(n0, max_total))
    per = None
    while True:
        t0 = time.perf_counter()
        acc += fn(n)
        total += n
        t1 = time.perf_counter()
        per = (t1 - t0) / n
        if total >= max_total:
            break
        can = int((deadline - t1) / max(per, 1e-9))
        if can < 96:
            break
        n = min(can, 1024, max_total - total)
        if n < 64:
            break
    return acc, total, per


# --------------------------------------------------------------------------
# Preflop equity table: equity (per mille) of every 3-card hand class against a
# uniformly random 3-card hand, both sides keeping their best two on the flop
# (same model as chunk_preflop; 12000 Monte Carlo samples per class, generated
# offline with this file's own simulator). Key: canon_key(); 1755 classes.
# --------------------------------------------------------------------------
_PRE_RAW = """
202122=325 302021=414 302122=406 303120=415 303122=418 303132=358 402021=412 402122=405
403020=344 403021=351 403031=439 403120=321 403121=322 403122=323 403132=441 404120=455
404122=451 404130=454 404132=450 404142=393 502021=418 502122=412 503020=355 503021=359
503031=441 503120=333 503121=325 503122=327 503132=452 504020=378 504021=382 504030=369
504031=369 504041=476 504120=345 504121=353 504122=354 504130=349 504131=336 504132=342
504142=466 505120=490 505122=480 505130=489 505132=489 505140=490 505142=492 505152=428
602021=424 602122=418 603020=355 603021=361 603031=438 603120=332 603121=332 603122=328
603132=446 604020=373 604021=375 604030=372 604031=371 604041=475 604120=352 604121=342
604122=347 604130=348 604131=351 604132=346 604142=477 605020=392 605021=390 605030=390
605031=386 605040=382 605041=389 605051=510 605120=364 605121=377 605122=368 605130=363
605131=358 605132=360 605140=360 605141=357 605142=350 605152=507 606120=507 606122=510
606130=530 606132=516 606140=519 606142=517 606150=519 606152=525 606162=473 702021=423
702122=430 703020=352 703021=365 703031=451 703120=337 703121=337 703122=339 703132=450
704020=384 704021=380 704030=381 704031=381 704041=481 704120=356 704121=347 704122=348
704130=350 704131=357 704132=349 704142=482 705020=398 705021=398 705030=396 705031=389
705040=389 705041=396 705051=511 705120=381 705121=378 705122=372 705130=375 705131=366
705132=372 705140=374 705141=367 705142=366 705152=511 706020=411 706021=408 706030=410
706031=410 706040=411 706041=399 706050=398 706051=405 706061=544 706120=395 706121=388
706122=387 706130=382 706131=381 706132=383 706140=382 706141=374 706142=377 706150=376
706151=381 706152=382 706162=539 707120=553 707122=546 707130=550 707132=541 707140=555
707142=551 707150=554 707152=557 707160=560 707162=556 707172=507 802021=427 802122=427
803020=360 803021=368 803031=467 803120=341 803121=331 803122=328 803132=454 804020=380
804021=386 804030=386 804031=388 804041=487 804120=360 804121=357 804122=357 804130=361
804131=354 804132=349 804142=482 805020=394 805021=403 805030=403 805031=399 805040=396
805041=404 805051=523 805120=374 805121=376 805122=366 805130=380 805131=383 805132=383
805140=370 805141=380 805142=370 805152=522 806020=407 806021=412 806030=413 806031=418
806040=406 806041=421 806050=408 806051=414 806061=547 806120=386 806121=395 806122=385
806130=394 806131=395 806132=391 806140=391 806141=395 806142=389 806150=390 806151=390
806152=389 806162=534 807020=416 807021=432 807030=422 807031=437 807040=421 807041=433
807050=424 807051=430 807060=418 807061=435 807071=571 807120=411 807121=410 807122=398
807130=410 807131=412 807132=408 807140=403 807141=409 807142=396 807150=403 807151=406
807152=396 807160=401 807161=405 807162=400 807172=575 808120=588 808122=590 808130=580
808132=584 808140=582 808142=587 808150=582 808152=581 808160=587 808162=587 808170=588
808172=589 808182=548 902021=434 902122=431 903020=377 903021=384 903031=462 903120=360
903121=350 903122=353 903132=462 904020=390 904021=390 904030=385 904031=391 904041=494
904120=367 904121=356 904122=357 904130=364 904131=356 904132=359 904142=490 905020=399
905021=406 905030=398 905031=408 905040=408 905041=409 905051=525 905120=378 905121=373
905122=377 905130=384 905131=383 905132=373 905140=388 905141=380 905142=388 905152=518
906020=411 906021=417 906030=417 906031=420 906040=416 906041=421 906050=416 906051=415
906061=557 906120=397 906121=390 906122=390 906130=404 906131=392 906132=385 906140=402
906141=393 906142=398 906150=405 906151=397 906152=396 906162=550 907020=428 907021=429
907030=422 907031=443 907040=434 907041=440 907050=441 907051=435 907060=429 907061=442
907071=578 907120=415 907121=404 907122=408 907130=408 907131=410 907132=407 907140=418
907141=416 907142=420 907150=419 907151=416 907152=414 907160=414 907161=418 907162=417
907172=584 908020=445 908021=457 908030=447 908031=454 908040=445 908041=454 908050=452
908051=453 908060=453 908061=455 908070=447 908071=444 908081=617 908120=421 908121=432
908122=427 908130=427 908131=432 908132=423 908140=435 908141=430 908142=434 908150=436
908151=430 908152=425 908160=432 908161=420 908162=434 908170=435 908171=428 908172=421
908182=612 909120=620 909122=617 909130=630 909132=619 909140=612 909142=628 909150=629
909152=619 909160=629 909162=622 909170=623 909172=622 909180=628 909182=625 909192=583
A02021=464 A02122=457 A03020=485 A03021=483 A03031=492 A03120=465 A03121=470 A03122=465
A03132=487 A04020=496 A04021=497 A04030=499 A04031=494 A04041=522 A04120=476 A04121=481
A04122=469 A04130=487 A04131=475 A04132=479 A04142=518 A05020=509 A05021=502 A05030=502
A05031=504 A05040=512 A05041=509 A05051=547 A05120=487 A05121=491 A05122=482 A05130=496
A05131=485 A05132=486 A05140=493 A05141=493 A05142=491 A05152=547 A06020=502 A06021=510
A06030=516 A06031=520 A06040=510 A06041=511 A06050=519 A06051=516 A06061=573 A06120=494
A06121=490 A06122=481 A06130=491 A06131=489 A06132=487 A06140=490 A06141=498 A06142=488
A06150=499 A06151=495 A06152=505 A06162=573 A07020=527 A07021=519 A07030=523 A07031=530
A07040=522 A07041=531 A07050=525 A07051=527 A07060=530 A07061=533 A07071=608 A07120=503
A07121=497 A07122=493 A07130=503 A07131=499 A07132=502 A07140=517 A07141=509 A07142=500
A07150=517 A07151=509 A07152=517 A07160=509 A07161=503 A07162=508 A07172=601 A08020=532
A08021=529 A08030=527 A08031=536 A08040=535 A08041=535 A08050=537 A08051=544 A08060=542
A08061=540 A08070=536 A08071=552 A08081=636 A08120=518 A08121=510 A08122=512 A08130=514
A08131=510 A08132=513 A08140=509 A08141=523 A08142=510 A08150=524 A08151=512 A08152=516
A08160=528 A08161=515 A08162=525 A08170=535 A08171=532 A08172=525 A08182=631 A09020=543
A09021=538 A09030=535 A09031=549 A09040=542 A09041=546 A09050=550 A09051=544 A09060=540
A09061=552 A09070=556 A09071=555 A09080=560 A09081=560 A09091=669 A09120=521 A09121=523
A09122=522 A09130=527 A09131=519 A09132=513 A09140=536 A09141=524 A09142=533 A09150=530
A09151=529 A09152=527 A09160=531 A09161=526 A09162=537 A09170=536 A09171=539 A09172=533
A09180=549 A09181=540 A09182=543 A09192=667 A0A120=800 A0A122=796 A0A130=809 A0A132=808
A0A140=805 A0A142=807 A0A150=810 A0A152=807 A0A160=804 A0A162=810 A0A170=803 A0A172=809
A0A180=796 A0A182=815 A0A190=811 A0A192=811 A0A1A2=787 A0A1J0=806 A0A1J2=805 A0A1K0=798
A0A1K2=801 A0A1Q0=805 A0A1Q2=813 A0A1T0=806 A0A1T2=806 A0J020=558 A0J021=562 A0J030=568
A0J031=576 A0J040=575 A0J041=582 A0J050=568 A0J051=580 A0J060=580 A0J061=587 A0J070=576
A0J071=587 A0J080=588 A0J081=595 A0J090=591 A0J091=604 A0J0J1=735 A0J0T0=595 A0J0T1=600
A0J120=551 A0J121=555 A0J122=548 A0J130=558 A0J131=561 A0J132=551 A0J140=564 A0J141=550
A0J142=552 A0J150=575 A0J151=556 A0J152=555 A0J160=569 A0J161=570 A0J162=565 A0J170=576
A0J171=567 A0J172=574 A0J180=586 A0J181=570 A0J182=569 A0J190=581 A0J191=578 A0J192=578
A0J1J2=738 A0J1T0=582 A0J1T1=584 A0J1T2=584 A0K020=583 A0K021=592 A0K030=592 A0K031=591
A0K040=596 A0K041=604 A0K050=595 A0K051=602 A0K060=607 A0K061=611 A0K070=611 A0K071=603
A0K080=608 A0K081=617 A0K090=616 A0K091=621 A0K0J0=617 A0K0J1=622 A0K0K1=799 A0K0Q0=625
A0K0Q1=627 A0K0T0=620 A0K0T1=627 A0K120=590 A0K121=578 A0K122=582 A0K130=579 A0K131=586
A0K132=576 A0K140=580 A0K141=582 A0K142=585 A0K150=590 A0K151=581 A0K152=585 A0K160=591
A0K161=588 A0K162=594 A0K170=600 A0K171=593 A0K172=588 A0K180=598 A0K181=599 A0K182=600
A0K190=607 A0K191=605 A0K192=610 A0K1J0=604 A0K1J1=609 A0K1J2=603 A0K1K2=791 A0K1Q0=610
A0K1Q1=611 A0K1Q2=609 A0K1T0=601 A0K1T1=601 A0K1T2=601 A0Q020=576 A0Q021=577 A0Q030=572
A0Q031=585 A0Q040=577 A0Q041=578 A0Q050=585 A0Q051=589 A0Q060=586 A0Q061=588 A0Q070=591
A0Q071=600 A0Q080=594 A0Q081=598 A0Q090=607 A0Q091=612 A0Q0J0=605 A0Q0J1=613 A0Q0Q1=766
A0Q0T0=598 A0Q0T1=600 A0Q120=568 A0Q121=561 A0Q122=564 A0Q130=568 A0Q131=571 A0Q132=565
A0Q140=569 A0Q141=583 A0Q142=570 A0Q150=584 A0Q151=570 A0Q152=569 A0Q160=578 A0Q161=576
A0Q162=573 A0Q170=582 A0Q171=580 A0Q172=581 A0Q180=589 A0Q181=590 A0Q182=592 A0Q190=602
A0Q191=589 A0Q192=593 A0Q1J0=590 A0Q1J1=595 A0Q1J2=603 A0Q1Q2=766 A0Q1T0=592 A0Q1T1=593
A0Q1T2=592 A0T020=554 A0T021=560 A0T030=560 A0T031=554 A0T040=557 A0T041=570 A0T050=568
A0T051=573 A0T060=570 A0T061=571 A0T070=565 A0T071=576 A0T080=581 A0T081=586 A0T090=574
A0T091=578 A0T0T1=706 A0T120=541 A0T121=544 A0T122=540 A0T130=544 A0T131=549 A0T132=538
A0T140=554 A0T141=546 A0T142=548 A0T150=551 A0T151=546 A0T152=544 A0T160=562 A0T161=554
A0T162=552 A0T170=561 A0T171=560 A0T172=563 A0T180=571 A0T181=563 A0T182=562 A0T190=572
A0T191=570 A0T192=562 A0T1T2=701 J02021=446 J02122=446 J03020=403 J03021=422 J03031=474
J03120=385 J03121=381 J03122=385 J03132=465 J04020=412 J04021=424 J04030=424 J04031=426
J04041=500 J04120=394 J04121=403 J04122=392 J04130=405 J04131=399 J04132=393 J04142=497
J05020=424 J05021=432 J05030=427 J05031=440 J05040=437 J05041=439 J05051=536 J05120=407
J05121=408 J05122=401 J05130=404 J05131=416 J05132=402 J05140=414 J05141=412 J05142=406
J05152=528 J06020=426 J06021=440 J06030=426 J06031=436 J06040=437 J06041=447 J06050=445
J06051=448 J06061=563 J06120=410 J06121=413 J06122=410 J06130=411 J06131=412 J06132=415
J06140=416 J06141=419 J06142=414 J06150=422 J06151=417 J06152=415 J06162=553 J07020=449
J07021=455 J07030=448 J07031=455 J07040=448 J07041=462 J07050=450 J07051=458 J07060=460
J07061=466 J07071=591 J07120=427 J07121=429 J07122=428 J07130=432 J07131=421 J07132=417
J07140=438 J07141=435 J07142=425 J07150=440 J07151=440 J07152=435 J07160=442 J07161=441
J07162=437 J07172=587 J08020=461 J08021=460 J08030=468 J08031=473 J08040=466 J08041=479
J08050=465 J08051=477 J08060=479 J08061=487 J08070=474 J08071=487 J08081=625 J08120=447
J08121=445 J08122=437 J08130=454 J08131=436 J08132=450 J08140=448 J08141=452 J08142=448
J08150=455 J08151=449 J08152=447 J08160=466 J08161=452 J08162=451 J08170=467 J08171=451
J08172=467 J08182=625 J09020=473 J09021=485 J09030=482 J09031=490 J09040=484 J09041=486
J09050=484 J09051=495 J09060=490 J09061=495 J09070=489 J09071=501 J09080=489 J09081=497
J09091=656 J09120=464 J09121=455 J09122=462 J09130=471 J09131=462 J09132=466 J09140=474
J09141=486 J09142=461 J09150=476 J09151=467 J09152=469 J09160=479 J09161=473 J09162=462
J09170=474 J09171=468 J09172=471 J09180=469 J09181=471 J09182=467 J09192=659 J0J120=697
J0J122=690 J0J130=696 J0J132=698 J0J140=694 J0J142=701 J0J150=697 J0J152=699 J0J160=695
J0J162=695 J0J170=698 J0J172=697 J0J180=701 J0J182=698 J0J190=695 J0J192=695 J0J1J2=677
J0J1T0=702 J0J1T2=703 J0T020=504 J0T021=503 J0T030=505 J0T031=507 J0T040=507 J0T041=515
J0T050=509 J0T051=518 J0T060=512 J0T061=518 J0T070=510 J0T071=519 J0T080=517 J0T081=522
J0T090=507 J0T091=523 J0T0T1=691 J0T120=491 J0T121=481 J0T122=489 J0T130=494 J0T131=488
J0T132=485 J0T140=492 J0T141=492 J0T142=488 J0T150=499 J0T151=498 J0T152=499 J0T160=498
J0T161=506 J0T162=494 J0T170=501 J0T171=499 J0T172=496 J0T180=490 J0T181=500 J0T182=496
J0T190=504 J0T191=495 J0T192=497 J0T1T2=685 K02021=457 K02122=455 K03020=446 K03021=456
K03031=483 K03120=440 K03121=436 K03122=420 K03132=485 K04020=458 K04021=463 K04030=467
K04031=467 K04041=511 K04120=443 K04121=444 K04122=428 K04130=452 K04131=442 K04132=438
K04142=510 K05020=469 K05021=465 K05030=461 K05031=475 K05040=476 K05041=482 K05051=538
K05120=448 K05121=454 K05122=445 K05130=458 K05131=454 K05132=451 K05140=457 K05141=456
K05142=457 K05152=534 K06020=475 K06021=484 K06030=470 K06031=488 K06040=486 K06041=486
K06050=486 K06051=492 K06061=572 K06120=463 K06121=464 K06122=452 K06130=460 K06131=466
K06132=459 K06140=475 K06141=457 K06142=466 K06150=470 K06151=478 K06152=459 K06162=565
K07020=485 K07021=490 K07030=483 K07031=491 K07040=489 K07041=496 K07050=496 K07051=499
K07060=496 K07061=493 K07071=604 K07120=462 K07121=459 K07122=468 K07130=464 K07131=464
K07132=473 K07140=474 K07141=481 K07142=475 K07150=478 K07151=476 K07152=474 K07160=483
K07161=479 K07162=483 K07172=601 K08020=495 K08021=496 K08030=499 K08031=501 K08040=502
K08041=494 K08050=506 K08051=500 K08060=505 K08061=511 K08070=516 K08071=518 K08081=636
K08120=477 K08121=474 K08122=473 K08130=478 K08131=480 K08132=478 K08140=478 K08141=480
K08142=480 K08150=484 K08151=473 K08152=484 K08160=495 K08161=484 K08162=489 K08170=493
K08171=497 K08172=503 K08182=620 K09020=507 K09021=511 K09030=514 K09031=518 K09040=512
K09041=516 K09050=528 K09051=523 K09060=531 K09061=532 K09070=527 K09071=527 K09080=536
K09081=539 K09091=665 K09120=498 K09121=496 K09122=485 K09130=495 K09131=497 K09132=490
K09140=498 K09141=508 K09142=503 K09150=504 K09151=494 K09152=500 K09160=513 K09161=520
K09162=504 K09170=515 K09171=513 K09172=512 K09180=525 K09181=512 K09182=510 K09192=664
K0J020=544 K0J021=538 K0J030=543 K0J031=560 K0J040=540 K0J041=546 K0J050=556 K0J051=564
K0J060=550 K0J061=560 K0J070=555 K0J071=572 K0J080=556 K0J081=564 K0J090=559 K0J091=568
K0J0J1=728 K0J0T0=570 K0J0T1=572 K0J120=534 K0J121=527 K0J122=523 K0J130=532 K0J131=524
K0J132=521 K0J140=538 K0J141=534 K0J142=528 K0J150=539 K0J151=540 K0J152=543 K0J160=539
K0J161=535 K0J162=534 K0J170=536 K0J171=547 K0J172=538 K0J180=551 K0J181=555 K0J182=546
K0J190=541 K0J191=554 K0J192=553 K0J1J2=716 K0J1T0=542 K0J1T1=554 K0J1T2=546 K0K120=770
K0K122=769 K0K130=770 K0K132=768 K0K140=765 K0K142=771 K0K150=765 K0K152=770 K0K160=764
K0K162=774 K0K170=764 K0K172=775 K0K180=774 K0K182=774 K0K190=774 K0K192=776 K0K1J0=769
K0K1J2=770 K0K1K2=748 K0K1Q0=771 K0K1Q2=776 K0K1T0=765 K0K1T2=772 K0Q020=553 K0Q021=561
K0Q030=551 K0Q031=558 K0Q040=562 K0Q041=563 K0Q050=556 K0Q051=563 K0Q060=563 K0Q061=569
K0Q070=567 K0Q071=578 K0Q080=576 K0Q081=579 K0Q090=570 K0Q091=576 K0Q0J0=572 K0Q0J1=584
K0Q0Q1=762 K0Q0T0=576 K0Q0T1=583 K0Q120=548 K0Q121=544 K0Q122=538 K0Q130=547 K0Q131=532
K0Q132=532 K0Q140=548 K0Q141=543 K0Q142=539 K0Q150=549 K0Q151=541 K0Q152=547 K0Q160=555
K0Q161=551 K0Q162=554 K0Q170=561 K0Q171=559 K0Q172=556 K0Q180=567 K0Q181=562 K0Q182=566
K0Q190=576 K0Q191=561 K0Q192=559 K0Q1J0=568 K0Q1J1=564 K0Q1J2=564 K0Q1Q2=749 K0Q1T0=562
K0Q1T1=557 K0Q1T2=565 K0T020=540 K0T021=540 K0T030=535 K0T031=542 K0T040=535 K0T041=540
K0T050=537 K0T051=539 K0T060=541 K0T061=553 K0T070=546 K0T071=553 K0T080=552 K0T081=560
K0T090=553 K0T091=557 K0T0T1=699 K0T120=521 K0T121=519 K0T122=517 K0T130=519 K0T131=522
K0T132=517 K0T140=525 K0T141=520 K0T142=521 K0T150=527 K0T151=520 K0T152=515 K0T160=535
K0T161=528 K0T162=529 K0T170=529 K0T171=536 K0T172=530 K0T180=530 K0T181=544 K0T182=542
K0T190=529 K0T191=544 K0T192=538 K0T1T2=694 Q02021=451 Q02122=449 Q03020=425 Q03021=432
Q03031=484 Q03120=416 Q03121=411 Q03122=399 Q03132=484 Q04020=438 Q04021=445 Q04030=433
Q04031=442 Q04041=504 Q04120=417 Q04121=413 Q04122=406 Q04130=422 Q04131=422 Q04132=418
Q04142=505 Q05020=447 Q05021=451 Q05030=452 Q05031=449 Q05040=460 Q05041=457 Q05051=540
Q05120=432 Q05121=422 Q05122=428 Q05130=434 Q05131=428 Q05132=428 Q05140=432 Q05141=430
Q05142=430 Q05152=537 Q06020=457 Q06021=462 Q06030=465 Q06031=462 Q06040=461 Q06041=462
Q06050=470 Q06051=471 Q06061=565 Q06120=428 Q06121=429 Q06122=423 Q06130=436 Q06131=436
Q06132=435 Q06140=440 Q06141=439 Q06142=448 Q06150=450 Q06151=436 Q06152=441 Q06162=567
Q07020=458 Q07021=463 Q07030=464 Q07031=461 Q07040=455 Q07041=475 Q07050=466 Q07051=471
Q07060=470 Q07061=482 Q07071=596 Q07120=439 Q07121=440 Q07122=435 Q07130=451 Q07131=437
Q07132=436 Q07140=450 Q07141=453 Q07142=446 Q07150=444 Q07151=449 Q07152=449 Q07160=453
Q07161=456 Q07162=451 Q07172=588 Q08020=473 Q08021=477 Q08030=472 Q08031=491 Q08040=475
Q08041=488 Q08050=492 Q08051=502 Q08060=490 Q08061=498 Q08070=491 Q08071=499 Q08081=621
Q08120=449 Q08121=452 Q08122=454 Q08130=469 Q08131=466 Q08132=460 Q08140=462 Q08141=469
Q08142=454 Q08150=464 Q08151=465 Q08152=471 Q08160=475 Q08161=475 Q08162=465 Q08170=475
Q08171=478 Q08172=483 Q08182=621 Q09020=497 Q09021=498 Q09030=492 Q09031=502 Q09040=506
Q09041=507 Q09050=509 Q09051=502 Q09060=504 Q09061=513 Q09070=509 Q09071=516 Q09080=511
Q09081=520 Q09091=666 Q09120=475 Q09121=477 Q09122=470 Q09130=487 Q09131=476 Q09132=480
Q09140=482 Q09141=492 Q09142=479 Q09150=489 Q09151=490 Q09152=484 Q09160=493 Q09161=485
Q09162=489 Q09170=497 Q09171=494 Q09172=496 Q09180=497 Q09181=496 Q09182=490 Q09192=662
Q0J020=522 Q0J021=538 Q0J030=530 Q0J031=529 Q0J040=527 Q0J041=529 Q0J050=539 Q0J051=537
Q0J060=540 Q0J061=541 Q0J070=535 Q0J071=547 Q0J080=547 Q0J081=541 Q0J090=538 Q0J091=549
Q0J0J1=721 Q0J0T0=540 Q0J0T1=550 Q0J120=512 Q0J121=511 Q0J122=516 Q0J130=511 Q0J131=509
Q0J132=515 Q0J140=515 Q0J141=518 Q0J142=522 Q0J150=516 Q0J151=518 Q0J152=519 Q0J160=524
Q0J161=525 Q0J162=520 Q0J170=533 Q0J171=535 Q0J172=532 Q0J180=527 Q0J181=525 Q0J182=535
Q0J190=525 Q0J191=527 Q0J192=525 Q0J1J2=727 Q0J1T0=524 Q0J1T1=529 Q0J1T2=522 Q0Q120=726
Q0Q122=739 Q0Q130=736 Q0Q132=740 Q0Q140=731 Q0Q142=728 Q0Q150=735 Q0Q152=732 Q0Q160=727
Q0Q162=731 Q0Q170=740 Q0Q172=738 Q0Q180=736 Q0Q182=737 Q0Q190=741 Q0Q192=736 Q0Q1J0=739
Q0Q1J2=735 Q0Q1Q2=708 Q0Q1T0=732 Q0Q1T2=736 Q0T020=514 Q0T021=520 Q0T030=521 Q0T031=513
Q0T040=529 Q0T041=527 Q0T050=516 Q0T051=530 Q0T060=529 Q0T061=534 Q0T070=532 Q0T071=537
Q0T080=533 Q0T081=535 Q0T090=524 Q0T091=541 Q0T0T1=693 Q0T120=493 Q0T121=500 Q0T122=489
Q0T130=508 Q0T131=500 Q0T132=506 Q0T140=503 Q0T141=504 Q0T142=501 Q0T150=509 Q0T151=510
Q0T152=511 Q0T160=518 Q0T161=515 Q0T162=510 Q0T170=524 Q0T171=523 Q0T172=511 Q0T180=512
Q0T181=522 Q0T182=511 Q0T190=523 Q0T191=505 Q0T192=507 Q0T1T2=689 T02021=441 T02122=441
T03020=394 T03021=389 T03031=462 T03120=375 T03121=376 T03122=366 T03132=461 T04020=402
T04021=406 T04030=410 T04031=406 T04041=496 T04120=387 T04121=384 T04122=373 T04130=385
T04131=381 T04132=374 T04142=493 T05020=401 T05021=401 T05030=414 T05031=416 T05040=417
T05041=417 T05051=525 T05120=388 T05121=383 T05122=380 T05130=383 T05131=387 T05132=390
T05140=392 T05141=391 T05142=392 T05152=522 T06020=418 T06021=429 T06030=422 T06031=431
T06040=427 T06041=434 T06050=433 T06051=434 T06061=557 T06120=416 T06121=391 T06122=390
T06130=404 T06131=403 T06132=395 T06140=406 T06141=414 T06142=405 T06150=415 T06151=415
T06152=414 T06162=555 T07020=438 T07021=439 T07030=440 T07031=448 T07040=448 T07041=446
T07050=446 T07051=454 T07060=444 T07061=447 T07071=582 T07120=413 T07121=415 T07122=422
T07130=423 T07131=423 T07132=418 T07140=428 T07141=418 T07142=427 T07150=432 T07151=429
T07152=421 T07160=427 T07161=426 T07162=423 T07172=586 T08020=465 T08021=467 T08030=455
T08031=455 T08040=461 T08041=463 T08050=465 T08051=471 T08060=469 T08061=470 T08070=458
T08071=463 T08081=609 T08120=441 T08121=442 T08122=427 T08130=436 T08131=445 T08132=434
T08140=459 T08141=440 T08142=440 T08150=447 T08151=442 T08152=442 T08160=447 T08161=440
T08162=438 T08170=444 T08171=446 T08172=438 T08182=617 T09020=470 T09021=472 T09030=477
T09031=484 T09040=480 T09041=478 T09050=487 T09051=490 T09060=479 T09061=481 T09070=476
T09071=485 T09080=478 T09081=483 T09091=644 T09120=451 T09121=455 T09122=457 T09130=460
T09131=451 T09132=452 T09140=464 T09141=454 T09142=455 T09150=462 T09151=470 T09152=465
T09160=467 T09161=458 T09162=468 T09170=471 T09171=458 T09172=459 T09180=451 T09181=461
T09182=457 T09192=647 T0T120=664 T0T122=658 T0T130=650 T0T132=666 T0T140=660 T0T142=668
T0T150=668 T0T152=668 T0T160=662 T0T162=659 T0T170=661 T0T172=668 T0T180=668 T0T182=670
T0T190=661 T0T192=664 T0T1T2=628
"""
PRE_TABLE = {}
for _tok in _PRE_RAW.split():
    _k, _v = _tok.split("=")
    PRE_TABLE[_k] = int(_v) / 1000.0


# --------------------------------------------------------------------------
# Quick (sample-free) strength, used only in emergency / low-time mode
# --------------------------------------------------------------------------
_CAT_EQ = [0.33, 0.58, 0.76, 0.85, 0.89, 0.91, 0.95, 0.99, 0.99]


def quick_equity(hole, board):
    try:
        if len(hole) >= 3 and len(board) == 0:
            r = sorted((c >> 2 for c in hole), reverse=True)
            s = [c & 3 for c in hole]
            eq = 0.30 + 0.018 * r[0] + 0.008 * r[1] + 0.004 * r[2]
            if r[0] == r[1] or r[1] == r[2]:
                eq += 0.07
            if r[0] == r[1] == r[2]:
                eq += 0.11
            mx = max(s.count(x) for x in set(s))
            eq += {1: 0.0, 2: 0.02, 3: 0.04}[mx]
            return min(0.9, eq)
        if len(board) < 3:
            return 0.45
        h = list(hole)
        if len(h) == 3:
            fl = np.array([board[:3]], dtype=np.int8)
            h = [int(x) for x in heuristic_keep(np.array([h], dtype=np.int8), fl)[0]]
        full = np.array([h + list(board)], dtype=np.int8)
        cat = int(eval_cards(full)[0]) // CAT
        bcat = int(eval_cards(np.array([list(board)], dtype=np.int8))[0]) // CAT if len(board) >= 5 else 0
        eq = _CAT_EQ[cat]
        if cat <= bcat and cat < 4:
            eq -= 0.12
        else:
            top = max(c >> 2 for c in h)
            eq += 0.004 * (top - 6) if cat == 0 else 0.0
        return max(0.05, min(0.99, eq))
    except Exception:
        return 0.4


# --------------------------------------------------------------------------
# Strategy constants
# --------------------------------------------------------------------------
# sample caps (the time budget is the other limit)
MAX_SAMPLES_FLOP = 10000
MAX_SAMPLES_POST = 12000

# preflop (equity vs a random 3-card hand with modelled discards)
PRE_OPEN = 0.495      # button: raise first in (about the top half of hands)
PRE_LIMP = 0.430      # button: complete the small blind (else fold)
PRE_ISO = 0.545       # big blind after a limp: raise
PRE_OPEN_TO = 6       # standard open (3 big blinds)
PRE_ISO_TO = 8

# postflop value bets: (min equity, fraction of pot), checked top-down.
# After the discard the opponent is modelled as a *uniformly random* 2-card hand,
# which is weaker than a real kept hand, so turn/river thresholds are higher.
BET_TABLE = {
    "flop": ((0.90, 1.00), (0.82, 0.75), (0.72, 0.50), (0.64, 0.33)),
    "turn": ((0.94, 1.00), (0.88, 0.75), (0.80, 0.50), (0.70, 0.33)),
    "river": ((0.95, 1.00), (0.90, 0.75), (0.82, 0.50), (0.72, 0.33)),
}

# facing a bet: call if equity >= pot odds + margin (margin grows with bet size)
MARGIN_BASE = 0.10
MARGIN_PER_POT = 0.15  # times bet/pot (capped at 1.5)
MARGIN_STREET = {"flop": 0.0, "turn": 0.05, "river": 0.07}
PRE_MARGIN_BASE = 0.06
PRE_MARGIN_PER_POT = 0.06
PRE_MARGIN_PER_RAISE = 0.06   # extra for every re-raise beyond a normal open
RAISE_EQ = {"preflop": 0.62, "flop": 0.84, "turn": 0.90, "river": 0.92}
MAX_REQ = 0.93


# --------------------------------------------------------------------------
# The bot
# --------------------------------------------------------------------------
def log(*a):
    try:
        if os.environ.get("BOT_DEBUG"):
            sys.stderr.write(" ".join(str(x) for x in a)[:300] + "\n")
            sys.stderr.flush()
    except Exception:
        pass


class Bot:
    def __init__(self):
        self.total_hands = 400
        self.bank_ms = 60000
        self.time_left_ms = 60000
        self.hand_id = 0
        self.seat = "button"
        self.hole = []
        self.dead = []
        self.rng = np.random.default_rng()
        # seconds per sample estimates (seeded by warmup)
        self.est = {"post": 3e-6, "flop": 5e-6, "pre": 5e-6}
        self.errors = 0

    # ---- warm-up (inside the 5 s start-up window, not charged) ----
    def warmup(self):
        """Touch every code path once with tiny batches so first use is not slow."""
        rng = self.rng
        build_tables()
        my = [c2i("As"), c2i("Kd"), c2i("7c")]
        flop = [c2i("Ah"), c2i("7d"), c2i("2s")]
        chunk_preflop(32, my, make_pool(my), rng)
        chunk_flop(32, my, flop, make_pool(my + flop), rng)
        extra = [c2i("Qs"), c2i("3c"), c2i("4h")]
        chunk_post(32, my[:2], flop, make_pool(my[:2] + flop + extra[:2]), rng)
        exact_river(my[:2], flop + extra[:2], make_pool(my[:2] + flop + extra[:2] + [c2i("9d"), c2i("9c")]))
        quick_equity(my, [])
        quick_equity(my[:2], flop)

    # ---- time budget ----
    def budget(self, time_left_ms, weight=1.0):
        """Seconds we may spend on this decision."""
        remaining = max(self.total_hands - self.hand_id + 1, 25)
        usable = time_left_ms - 1500.0 - 12.0 * remaining
        if usable <= 0:
            return 0.0
        # worst case ~4 plain decisions + 1 discard (weight 1.6) per hand = 5.6 units
        per = usable * 0.55 / (remaining * 5.6) * weight  # ms
        return min(per, 60.0 * weight) / 1000.0

    # ---- message dispatch ----
    def handle(self, msg):
        t = msg.get("type")
        if t == "init":
            self.total_hands = int(msg.get("total_hands", 400) or 400)
            self.bank_ms = int(msg.get("time_bank_ms", 60000) or 60000)
            self.time_left_ms = self.bank_ms
        elif t == "new_hand":
            self.hand_id = int(msg.get("hand_id", self.hand_id + 1))
            self.seat = msg.get("seat", "button")
            self.hole = []
            self.dead = []
            self.hole = [c2i(c) for c in msg.get("hole_cards", [])]
        elif t == "action_request":
            return self.on_action(msg)
        elif t == "discard_request":
            return self.on_discard(msg)
        elif t == "discard_result":
            self.dead = []
            for key in ("my_discard", "opp_discard"):
                v = msg.get(key)
                if v:
                    self.dead.append(c2i(v))
            hc = msg.get("hole_cards")
            if hc:
                self.hole = [c2i(c) for c in hc]
        return None

    # ---- discard ----
    def on_discard(self, req):
        tl = req.get("time_left_ms")
        if tl is not None:
            self.time_left_ms = float(tl)
        hc = req.get("hole_cards")
        hole = [c2i(c) for c in hc] if hc else list(self.hole)
        if not hole:
            return None  # nothing sensible to say; the engine discards for us
        board = [c2i(c) for c in req.get("board", [])]
        self.hole = hole
        try:
            card = self.pick_discard(hole, board, self.time_left_ms)
        except Exception as e:  # never let a discard fail
            log("discard error", repr(e))
            card = self.fallback_discard(hole)
        return {"type": "discard", "card": i2c(card)}

    @staticmethod
    def fallback_discard(hole):
        """Drop the lowest-ranked card (same as the engine's own correction)."""
        return min(hole, key=lambda c: (c >> 2, c & 3))

    def pick_discard(self, hole, board, time_left_ms):
        if len(hole) != 3 or len(board) != 3:
            return self.fallback_discard(hole)
        budget = self.budget(time_left_ms, weight=1.6)
        if budget < 0.003:
            # no time for simulation: keep the best two by flop strength
            h = np.array([hole], dtype=np.int8)
            fl = np.array([board], dtype=np.int8)
            kept = set(int(x) for x in heuristic_keep(h, fl)[0])
            for c in hole:
                if c not in kept:
                    return c
            return self.fallback_discard(hole)
        sums, total, per = self.simulate_flop(hole, board, budget)
        j = int(np.argmax(sums))
        return hole[j]  # option j drops card j

    def simulate_flop(self, hole, board, budget):
        pool = make_pool(hole + board)
        deadline = time.perf_counter() + budget
        n0 = int(min(1024, max(128, budget * 0.4 / max(self.est["flop"], 1e-7))))
        sums, total, per = run_chunks(
            lambda n: chunk_flop(n, hole, board, pool, self.rng), 3, deadline, n0, MAX_SAMPLES_FLOP)
        self.est["flop"] = 0.5 * self.est["flop"] + 0.5 * per
        return sums, total, per

    # ---- equity ----
    def equity(self, hole, board, budget):
        """Equity vs a uniformly random opponent hand (win + tie/2)."""
        if len(hole) == 3 and len(board) == 0:
            v = PRE_TABLE.get(canon_key(hole))
            if v is not None:
                return v
        if budget < 0.0025:
            return quick_equity(hole, board)
        deadline = time.perf_counter() + budget
        if len(hole) == 3 and len(board) == 0:
            pool = make_pool(hole)
            n0 = int(min(1024, max(128, budget * 0.4 / max(self.est["pre"], 1e-7))))
            sums, total, per = run_chunks(
                lambda n: chunk_preflop(n, hole, pool, self.rng), 1, deadline, n0, MAX_SAMPLES_FLOP)
            self.est["pre"] = 0.5 * self.est["pre"] + 0.5 * per
            return float(sums[0] / total)
        if len(hole) == 3 and len(board) == 3:
            sums, total, per = self.simulate_flop(hole, board, budget)
            return float((sums / total).max())
        if len(hole) == 3:
            # discard result was missed: keep the best two with the flop heuristic
            h = np.array([hole], dtype=np.int8)
            fl = np.array([board[:3]], dtype=np.int8)
            hole = [int(x) for x in heuristic_keep(h, fl)[0]]
        pool = make_pool(list(hole) + list(board) + list(self.dead))
        if len(board) == 5:
            return exact_river(hole, board, pool)
        n0 = int(min(1024, max(128, budget * 0.4 / max(self.est["post"], 1e-7))))
        sums, total, per = run_chunks(
            lambda n: chunk_post(n, hole, board, pool, self.rng), 1, deadline, n0, MAX_SAMPLES_POST)
        self.est["post"] = 0.5 * self.est["post"] + 0.5 * per
        return float(sums[0] / total)

    # ---- betting ----
    def on_action(self, req):
        tl = req.get("time_left_ms")
        if tl is not None:
            self.time_left_ms = float(tl)
        try:
            board = [c2i(c) for c in req.get("board", [])]
            if len(self.hole) < 2:
                raise ValueError("no hole cards")
            t0 = time.perf_counter()
            bud = self.budget(self.time_left_ms)
            eq = self.equity(list(self.hole), board, bud)
            act = self.policy(req, eq)
            log("act h%s %s bud=%.1fms used=%.1fms left=%d eq=%.3f -> %s" % (
                self.hand_id, req.get("street"), bud * 1e3, (time.perf_counter() - t0) * 1e3,
                self.time_left_ms, eq, act))
        except Exception as e:
            log("action error", repr(e))
            act = self.fallback_action(req)
        return self.sanitize(act, req)

    @staticmethod
    def fallback_action(req):
        legal = req.get("legal_actions") or []
        if "check" in legal:
            return {"type": "action", "action": "check"}
        pot = req.get("pot", 0) or 0
        to_call = req.get("to_call", 0) or 0
        if "call" in legal and to_call <= max(2, 0.15 * pot):
            return {"type": "action", "action": "call"}
        if "fold" in legal:
            return {"type": "action", "action": "fold"}
        if "call" in legal:
            return {"type": "action", "action": "call"}
        return {"type": "action", "action": "check"}

    def sanitize(self, act, req):
        """Make sure the reply is legal; otherwise fall back."""
        try:
            legal = req.get("legal_actions") or []
            a = act.get("action")
            if a not in legal:
                return self.fallback_action(req)
            if a == "raise":
                lo = int(req.get("min_raise"))
                hi = int(req.get("max_raise"))
                amt = int(act.get("amount", lo))
                amt = max(lo, min(hi, amt))
                return {"type": "action", "action": "raise", "amount": amt}
            return {"type": "action", "action": a}
        except Exception:
            return self.fallback_action(req)

    @staticmethod
    def raise_to(req, target):
        lo = int(req["min_raise"])
        hi = int(req["max_raise"])
        t = int(round(target))
        t = max(lo, min(hi, t))
        # if the raise commits most of what is left, just get it all in
        my_bet = req.get("my_bet", 0) or 0
        my_stack = req.get("my_stack", 0) or 0
        left_after = my_bet + my_stack - t
        if hi - t <= 0.30 * (hi - my_bet) or left_after < 0.25 * (req.get("pot", 0) + (t - my_bet)):
            t = hi
        return {"type": "action", "action": "raise", "amount": t}

    def policy(self, req, eq):
        legal = req.get("legal_actions") or []
        street = req.get("street", "preflop")
        pot = int(req.get("pot", 0) or 0)
        to_call = int(req.get("to_call", 0) or 0)
        my_bet = int(req.get("my_bet", 0) or 0)
        opp_bet = int(req.get("opp_bet", 0) or 0)
        raises_left = req.get("raises_left")
        can_raise = "raise" in legal and req.get("min_raise") is not None and req.get("max_raise") is not None
        CHECK = {"type": "action", "action": "check"}
        CALL = {"type": "action", "action": "call"}
        FOLD = {"type": "action", "action": "fold"}

        # ---------------- preflop openings ----------------
        if street == "preflop":
            if to_call <= 0:
                # big blind after a limp (or any free check)
                if can_raise and eq >= PRE_ISO:
                    return self.raise_to(req, PRE_ISO_TO if eq < 0.62 else PRE_ISO_TO + 4)
                return CHECK
            if my_bet == 1 and opp_bet == 2 and to_call == 1:
                # small blind, first to act
                if can_raise and eq >= PRE_OPEN:
                    return self.raise_to(req, PRE_OPEN_TO if eq < 0.62 else PRE_OPEN_TO + 2)
                if eq >= PRE_LIMP:
                    return CALL
                return FOLD if "fold" in legal else CALL

        # ---------------- no bet to face ----------------
        if to_call <= 0:
            if can_raise:
                for thr, frac in BET_TABLE.get(street, BET_TABLE["river"]):
                    if eq >= thr:
                        return self.raise_to(req, opp_bet + max(2, frac * pot))
            return CHECK

        # ---------------- facing a bet or raise ----------------
        need = to_call / float(pot + to_call)
        f = min(to_call / float(max(pot - to_call, 1)), 1.5 if street != "preflop" else 2.0)
        if street == "preflop":
            n_raises = 4 - int(raises_left) if raises_left is not None else 2
            margin = PRE_MARGIN_BASE + PRE_MARGIN_PER_POT * f + PRE_MARGIN_PER_RAISE * max(0, n_raises - 2)
        else:
            margin = MARGIN_BASE + MARGIN_PER_POT * f + MARGIN_STREET.get(street, 0.05)
        req_eq = min(need + margin, MAX_REQ)
        if eq < req_eq:
            return FOLD if "fold" in legal else CALL
        if can_raise and eq >= RAISE_EQ.get(street, 0.9) and eq >= req_eq + 0.10:
            if street == "preflop":
                target = opp_bet * 3 + 1
            else:
                frac = 1.0 if eq >= 0.94 else 0.75
                target = opp_bet + frac * (pot + to_call)
            return self.raise_to(req, target)
        return CALL


# --------------------------------------------------------------------------
# I/O loop
# --------------------------------------------------------------------------
def send(obj):
    sys.stdout.write(json.dumps(obj, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def safe_reply(bot, msg):
    """Reply used if handle() itself raised."""
    t = msg.get("type")
    try:
        if t == "action_request":
            return bot.sanitize(bot.fallback_action(msg), msg)
        if t == "discard_request":
            hole = [c2i(c) for c in msg["hole_cards"]]
            return {"type": "discard", "card": i2c(bot.fallback_discard(hole))}
    except Exception:
        pass
    if t == "action_request":
        return {"type": "action", "action": "check" if "check" in (msg.get("legal_actions") or []) else "fold"}
    if t == "discard_request":
        try:
            return {"type": "discard", "card": msg["hole_cards"][0]}
        except Exception:
            return None
    return None


def main():
    bot = Bot()
    try:
        bot.warmup()
    except Exception as e:
        log("warmup error", repr(e))
    while True:
        try:
            raw = sys.stdin.buffer.readline()
        except Exception:
            break
        if not raw:
            break  # EOF: the engine is gone
        line = raw.decode("utf-8", "replace").strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if not isinstance(msg, dict):
            continue
        if msg.get("type") == "match_end":
            break
        try:
            reply = bot.handle(msg)
        except Exception as e:
            log("handle error", repr(e))
            reply = safe_reply(bot, msg)
        if reply is not None:
            try:
                send(reply)
            except (BrokenPipeError, OSError):
                break
            except Exception:
                pass


if __name__ == "__main__":
    main()
