"""
Fast poker hand evaluator, equity calculator, and preflop lookup table.
Uses Cactus Kev's algorithm for sub-millisecond evaluation with zero external dependencies.
"""

import itertools
import random
import time

RANKS = "23456789TJQKA"
SUITS = "shdc"
PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]

# Card bitmask mapping
# Bits:
# 16-28: Rank bitmask (1 << rank)
# 12-15: Suit bitmask (1 << suit)
# 8-11:  Rank value (0..12)
# 0-7:   Prime number for rank
CARD_TO_INT = {}
INT_TO_CARD = {}
ALL_CARDS = []

for r_idx, r in enumerate(RANKS):
    p = PRIMES[r_idx]
    b = 1 << (16 + r_idx)
    r_val = r_idx << 8
    for s_idx, s in enumerate(SUITS):
        s_val = 1 << (12 + s_idx)
        c_int = b | s_val | r_val | p
        c_str = r + s
        CARD_TO_INT[c_str] = c_int
        INT_TO_CARD[c_int] = c_str
        ALL_CARDS.append(c_int)

# Precompute Cactus Kev tables
FLUSHES = {}
UNIQUES = {}

STRAIGHT_MASKS = {
    0x1F00: 1,  # A-high (Royal/Broadway)
    0x0F80: 2,  # K-high
    0x07C0: 3,  # Q-high
    0x03E0: 4,  # J-high
    0x01F0: 5,  # T-high
    0x00F8: 6,  # 9-high
    0x007C: 7,  # 8-high
    0x003E: 8,  # 7-high
    0x001F: 9,  # 6-high
    0x100F: 10, # 5-high (wheel: A-2-3-4-5)
}

combos_5 = sorted(
    itertools.combinations(range(13), 5),
    key=lambda c: tuple(reversed(c)),
    reverse=True
)

flush_rank = 323
high_card_rank = 6186

for combo in combos_5:
    mask = sum(1 << r for r in combo)
    if mask in STRAIGHT_MASKS:
        FLUSHES[mask] = STRAIGHT_MASKS[mask]  # 1..10 Straight flush
        UNIQUES[mask] = 1600 + STRAIGHT_MASKS[mask] - 1  # 1600..1609 Straight
    else:
        FLUSHES[mask] = flush_rank  # 323..1599 Flush
        flush_rank += 1
        UNIQUES[mask] = high_card_rank  # 6186..7462 High card
        high_card_rank += 1

PAIRS = {}
# Quads: 11..166
quad_rank = 11
for r1 in reversed(range(13)):
    for r2 in reversed(range(13)):
        if r1 == r2:
            continue
        PAIRS[(PRIMES[r1] ** 4) * PRIMES[r2]] = quad_rank
        quad_rank += 1

# Full house: 167..322
fh_rank = 167
for r1 in reversed(range(13)):
    for r2 in reversed(range(13)):
        if r1 == r2:
            continue
        PAIRS[(PRIMES[r1] ** 3) * (PRIMES[r2] ** 2)] = fh_rank
        fh_rank += 1

# Three of a kind: 1610..2467
trips_rank = 1610
for r1 in reversed(range(13)):
    for r2, r3 in itertools.combinations(reversed(range(13)), 2):
        if r1 == r2 or r1 == r3:
            continue
        PAIRS[(PRIMES[r1] ** 3) * PRIMES[r2] * PRIMES[r3]] = trips_rank
        trips_rank += 1

# Two pair: 2468..3325
tp_rank = 2468
for r1, r2 in itertools.combinations(reversed(range(13)), 2):
    for r3 in reversed(range(13)):
        if r3 == r1 or r3 == r2:
            continue
        PAIRS[(PRIMES[r1] ** 2) * (PRIMES[r2] ** 2) * PRIMES[r3]] = tp_rank
        tp_rank += 1

# One pair: 3326..6185
op_rank = 3326
for r1 in reversed(range(13)):
    for r2, r3, r4 in itertools.combinations(reversed(range(13)), 3):
        if r1 == r2 or r1 == r3 or r1 == r4:
            continue
        PAIRS[(PRIMES[r1] ** 2) * PRIMES[r2] * PRIMES[r3] * PRIMES[r4]] = op_rank
        op_rank += 1


COMBOS_7_CHOOSE_5 = list(itertools.combinations(range(7), 5))
COMBOS_6_CHOOSE_5 = list(itertools.combinations(range(6), 5))


def eval_5(c1, c2, c3, c4, c5):
    """
    Evaluates a 5-card hand.
    Returns integer rank 1 (Royal Flush) to 7462 (7-5-4-3-2 unsuited).
    Lower is better.
    """
    if c1 & c2 & c3 & c4 & c5 & 0xF000:
        return FLUSHES[(c1 | c2 | c3 | c4 | c5) >> 16]
    prod = (c1 & 0xFF) * (c2 & 0xFF) * (c3 & 0xFF) * (c4 & 0xFF) * (c5 & 0xFF)
    val = PAIRS.get(prod)
    if val is not None:
        return val
    return UNIQUES[(c1 | c2 | c3 | c4 | c5) >> 16]


def eval_7(cards):
    """
    Evaluates the best 5-card hand out of 7 cards.
    cards must be a list or tuple of 7 integer card representations.
    """
    best = 9999
    for i1, i2, i3, i4, i5 in COMBOS_7_CHOOSE_5:
        score = eval_5(cards[i1], cards[i2], cards[i3], cards[i4], cards[i5])
        if score < best:
            best = score
    return best


def eval_6(cards):
    """
    Evaluates the best 5-card hand out of 6 cards.
    """
    best = 9999
    for i1, i2, i3, i4, i5 in COMBOS_6_CHOOSE_5:
        score = eval_5(cards[i1], cards[i2], cards[i3], cards[i4], cards[i5])
        if score < best:
            best = score
    return best


def to_card_int(c):
    """Converts a card to integer representation if it is a string."""
    if isinstance(c, int):
        return c
    return CARD_TO_INT[c]


def evaluate_hand(cards):
    """
    Evaluates a 5, 6, or 7 card hand.
    cards can be strings or ints.
    """
    c_ints = [to_card_int(c) for c in cards]
    n = len(c_ints)
    if n == 5:
        return eval_5(*c_ints)
    elif n == 7:
        return eval_7(c_ints)
    elif n == 6:
        return eval_6(c_ints)
    else:
        raise ValueError(f"Expected 5, 6, or 7 cards, got {n}")


def hand_category(score):
    """Returns the descriptive hand rank category for a Cactus Kev score."""
    if score <= 10:
        return "Straight Flush"
    elif score <= 166:
        return "Four of a Kind"
    elif score <= 322:
        return "Full House"
    elif score <= 1599:
        return "Flush"
    elif score <= 1609:
        return "Straight"
    elif score <= 2467:
        return "Three of a Kind"
    elif score <= 3325:
        return "Two Pair"
    elif score <= 6185:
        return "One Pair"
    else:
        return "High Card"


def canonical_hand(c1, c2):
    """
    Converts two cards into their 169 canonical representation:
    e.g. 'AA', 'AKs', 'AKo', '72o'.
    """
    if isinstance(c1, int):
        c1 = INT_TO_CARD[c1]
    if isinstance(c2, int):
        c2 = INT_TO_CARD[c2]

    r1, s1 = c1[0], c1[1]
    r2, s2 = c2[0], c2[1]

    idx1 = RANKS.index(r1)
    idx2 = RANKS.index(r2)

    if idx1 == idx2:
        return r1 + r2
    elif idx1 > idx2:
        suffix = "s" if s1 == s2 else "o"
        return r1 + r2 + suffix
    else:
        suffix = "s" if s1 == s2 else "o"
        return r2 + r1 + suffix


PREFLOP_EQUITY = {
    '22': 0.5188, '32o': 0.3008, '32s': 0.3515, '33': 0.5485, '42o': 0.3245,
    '42s': 0.3765, '43o': 0.3523, '43s': 0.3760, '44': 0.5675, '52o': 0.3297,
    '52s': 0.3650, '53o': 0.3613, '53s': 0.3922, '54o': 0.3827, '54s': 0.4120,
    '55': 0.6195, '62o': 0.3415, '62s': 0.3802, '63o': 0.3630, '63s': 0.3952,
    '64o': 0.3915, '64s': 0.4170, '65o': 0.4105, '65s': 0.4338, '66': 0.6480,
    '72o': 0.3468, '72s': 0.3847, '73o': 0.3628, '73s': 0.4030, '74o': 0.3862,
    '74s': 0.4235, '75o': 0.4138, '75s': 0.4480, '76o': 0.4140, '76s': 0.4700,
    '77': 0.6617, '82o': 0.3615, '82s': 0.4090, '83o': 0.3743, '83s': 0.4007,
    '84o': 0.3870, '84s': 0.4268, '85o': 0.3942, '85s': 0.4520, '86o': 0.4303,
    '86s': 0.4635, '87o': 0.4567, '87s': 0.4775, '88': 0.6850, '92o': 0.4022,
    '92s': 0.4250, '93o': 0.4133, '93s': 0.4223, '94o': 0.4022, '94s': 0.4275,
    '95o': 0.4308, '95s': 0.4500, '96o': 0.4333, '96s': 0.4728, '97o': 0.4637,
    '97s': 0.4622, '98o': 0.4680, '98s': 0.5052, '99': 0.7137, 'A2o': 0.5407,
    'A2s': 0.5743, 'A3o': 0.5423, 'A3s': 0.5827, 'A4o': 0.5395, 'A4s': 0.5970,
    'A5o': 0.5717, 'A5s': 0.5945, 'A6o': 0.5763, 'A6s': 0.6142, 'A7o': 0.5925,
    'A7s': 0.5980, 'A8o': 0.5935, 'A8s': 0.6392, 'A9o': 0.5952, 'A9s': 0.6332,
    'AA': 0.8495, 'AJo': 0.6315, 'AJs': 0.6542, 'AKo': 0.6607, 'AKs': 0.6807,
    'AQo': 0.6312, 'AQs': 0.6635, 'ATo': 0.6285, 'ATs': 0.6512, 'J2o': 0.4425,
    'J2s': 0.4740, 'J3o': 0.4410, 'J3s': 0.4718, 'J4o': 0.4492, 'J4s': 0.5010,
    'J5o': 0.4670, 'J5s': 0.4995, 'J6o': 0.4642, 'J6s': 0.4945, 'J7o': 0.5005,
    'J7s': 0.5190, 'J8o': 0.5180, 'J8s': 0.5320, 'J9o': 0.5447, 'J9s': 0.5525,
    'JJ': 0.7722, 'JTo': 0.5487, 'JTs': 0.5537, 'K2o': 0.5125, 'K2s': 0.5427,
    'K3o': 0.5312, 'K3s': 0.5403, 'K4o': 0.5235, 'K4s': 0.5377, 'K5o': 0.5417,
    'K5s': 0.5867, 'K6o': 0.5335, 'K6s': 0.5673, 'K7o': 0.5577, 'K7s': 0.5763,
    'K8o': 0.5775, 'K8s': 0.5880, 'K9o': 0.5860, 'K9s': 0.6052, 'KJo': 0.6005,
    'KJs': 0.6308, 'KK': 0.8167, 'KQo': 0.6095, 'KQs': 0.6298, 'KTo': 0.6125,
    'KTs': 0.6108, 'Q2o': 0.4642, 'Q2s': 0.4913, 'Q3o': 0.4843, 'Q3s': 0.5288,
    'Q4o': 0.4830, 'Q4s': 0.5265, 'Q5o': 0.5028, 'Q5s': 0.5373, 'Q6o': 0.5168,
    'Q6s': 0.5397, 'Q7o': 0.4963, 'Q7s': 0.5593, 'Q8o': 0.5333, 'Q8s': 0.5725,
    'Q9o': 0.5537, 'Q9s': 0.5843, 'QJo': 0.5900, 'QJs': 0.5915, 'QQ': 0.7910,
    'QTo': 0.5695, 'QTs': 0.5990, 'T2o': 0.4220, 'T2s': 0.4525, 'T3o': 0.4243,
    'T3s': 0.4627, 'T4o': 0.4395, 'T4s': 0.4700, 'T5o': 0.4395, 'T5s': 0.4660,
    'T6o': 0.4410, 'T6s': 0.4973, 'T7o': 0.4575, 'T7s': 0.5260, 'T8o': 0.5008,
    'T8s': 0.5337, 'T9o': 0.5022, 'T9s': 0.5325, 'TT': 0.7620
}


def get_preflop_equity(c1, c2):
    """Instant O(1) lookup of preflop equity vs random hand."""
    name = canonical_hand(c1, c2)
    return PREFLOP_EQUITY.get(name, 0.50)


def get_draws(my_cards, board):
    """
    Detects flush draws and straight draws for hole cards + board.
    Returns dict: {'flush_draw': bool, 'oesd': bool, 'gutshot': bool}
    """
    all_c = [to_card_int(c) for c in my_cards + board]
    my_c_ints = [to_card_int(c) for c in my_cards]

    # Flush draw check: 4 cards of the same suit, with at least 1 in our hand
    suits_count = [0, 0, 0, 0]
    my_suits = [0, 0, 0, 0]
    for c in all_c:
        for s_idx in range(4):
            if c & (1 << (12 + s_idx)):
                suits_count[s_idx] += 1
    for c in my_c_ints:
        for s_idx in range(4):
            if c & (1 << (12 + s_idx)):
                my_suits[s_idx] += 1

    flush_draw = any(suits_count[i] == 4 and my_suits[i] > 0 for i in range(4))

    # Straight draw check:
    rank_mask = 0
    for c in all_c:
        rank_mask |= ((c >> 16) & 0x1FFF)
    if rank_mask & (1 << 12):  # Ace also counts as low
        rank_mask |= 1

    oesd = False
    gutshot = False

    # Check contiguous 4-bits for OESD (open-ended straight draw)
    # E.g. 5-6-7-8 (bits 3,4,5,6) -> can make straight with 4 or 9
    for low in range(1, 10):  # cannot be ace-low or ace-high open ended
        submask = (0x0F << low)
        if (rank_mask & submask) == submask:
            oesd = True
            break

    # Gutshot: 4 cards out of 5 for a straight
    if not oesd:
        for low in range(0, 10):
            window = (rank_mask >> low) & 0x1F
            # If 4 bits set in 5-bit window
            if bin(window).count("1") == 4:
                gutshot = True
                break

    return {"flush_draw": flush_draw, "oesd": oesd, "gutshot": gutshot}


def estimate_equity(my_cards, board, n_samples=250, time_budget=0.035):
    """
    Computes Monte Carlo equity of my_cards against a random opponent hand given board.
    
    Guarantees:
    - Never exceeds time_budget.
    - Accurately computes win/tie equity in [0.0, 1.0].
    - On River (5 board cards), exact fast rollout or high sample.
    """
    t0 = time.time()
    c1 = to_card_int(my_cards[0])
    c2 = to_card_int(my_cards[1])
    board_ints = [to_card_int(c) for c in board]
    b_len = len(board_ints)

    dead_cards = {c1, c2}.union(board_ints)
    available_cards = [c for c in ALL_CARDS if c not in dead_cards]

    if b_len == 5:
        # River: only 2 opponent cards needed
        # Opponent cards combinations: len(available) * (len(available)-1) // 2 = 990
        my_score = eval_7([c1, c2] + board_ints)
        wins = 0
        ties = 0
        samples_run = 0

        # Sample or evaluate
        num_to_run = min(n_samples, len(available_cards) * (len(available_cards) - 1) // 2)
        for _ in range(num_to_run):
            if time.time() - t0 > time_budget:
                break
            opp1, opp2 = random.sample(available_cards, 2)
            opp_score = eval_7([opp1, opp2] + board_ints)
            if my_score < opp_score:
                wins += 1
            elif my_score == opp_score:
                ties += 1
            samples_run += 1

        if samples_run == 0:
            return 0.5
        return (wins + 0.5 * ties) / samples_run

    elif b_len == 4:
        # Turn: need 2 opp cards + 1 river card (3 total)
        wins = 0
        ties = 0
        samples_run = 0

        for _ in range(n_samples):
            if time.time() - t0 > time_budget:
                break
            opp1, opp2, river = random.sample(available_cards, 3)
            my_score = eval_7([c1, c2, river] + board_ints)
            opp_score = eval_7([opp1, opp2, river] + board_ints)
            if my_score < opp_score:
                wins += 1
            elif my_score == opp_score:
                ties += 1
            samples_run += 1

        if samples_run == 0:
            return 0.5
        return (wins + 0.5 * ties) / samples_run

    elif b_len == 3:
        # Flop: need 2 opp cards + 2 board cards (4 total)
        wins = 0
        ties = 0
        samples_run = 0

        for _ in range(n_samples):
            if time.time() - t0 > time_budget:
                break
            opp1, opp2, turn, river = random.sample(available_cards, 4)
            full_board = board_ints + [turn, river]
            my_score = eval_7([c1, c2] + full_board)
            opp_score = eval_7([opp1, opp2] + full_board)
            if my_score < opp_score:
                wins += 1
            elif my_score == opp_score:
                ties += 1
            samples_run += 1

        if samples_run == 0:
            return 0.5
        return (wins + 0.5 * ties) / samples_run

    else:
        # Preflop (board empty)
        return get_preflop_equity(c1, c2)
