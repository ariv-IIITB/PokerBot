"""Cards, colex combination indices and the preflop canonical table (BUILDMAP §4.1, §4.2, §5.1.1)."""
import itertools
from math import comb

import numpy as np

RANKS = "23456789TJQKA"
SUITS = "shdc"              # the engine's SUITS order

N2 = comb(52, 2)            # 1,326
N3 = comb(52, 3)            # 22,100
N4 = comb(52, 4)            # 270,725
N_PRE = 1755                # canonical 3-card classes

# ---------------------------------------------------------------- §4.1 card ids

def rank(c):
    return c >> 2


def suit(c):
    return c & 3


def parse_card(s):
    """"As" -> 48, "2c" -> 3. Raises ValueError on anything else."""
    if not isinstance(s, str) or len(s) != 2 or s[0] not in RANKS or s[1] not in SUITS:
        raise ValueError(f"bad card: {s!r}")
    return RANKS.index(s[0]) * 4 + SUITS.index(s[1])


def format_card(c):
    return RANKS[c >> 2] + SUITS[c & 3]


def parse_cards(xs):
    return [parse_card(s) for s in xs]


def format_cards(cs):
    return [format_card(int(c)) for c in cs]


# ---------------------------------------------------------------- §4.2 colex indices
# Arguments may come in any order; they are sorted ascending first.

def idx2(a, b):
    if a > b:
        a, b = b, a
    return b * (b - 1) // 2 + a


def idx3(a, b, c):
    a, b, c = sorted((a, b, c))
    return comb(c, 3) + comb(b, 2) + a


def idx4(a, b, c, d):
    a, b, c, d = sorted((a, b, c, d))
    return comb(d, 4) + comb(c, 3) + comb(b, 2) + a


def _unrank(i, k):
    """Inverse of the colex index for k cards. Returns an ascending tuple."""
    out = []
    top = 52
    for j in range(k, 0, -1):
        c = top - 1
        while comb(c, j) > i:
            c -= 1
        out.append(c)
        i -= comb(c, j)
        top = c
    return tuple(reversed(out))


def unrank2(i):
    return _unrank(i, 2)


def unrank3(i):
    return _unrank(i, 3)


def unrank4(i):
    return _unrank(i, 4)


def idx2_array(a, b):
    """Vectorised idx2 for int arrays (any order within each pair)."""
    a = np.asarray(a, dtype=np.int64)
    b = np.asarray(b, dtype=np.int64)
    lo, hi = np.minimum(a, b), np.maximum(a, b)
    return hi * (hi - 1) // 2 + lo


# COMBO[i] = (a, b), a < b, in idx2 order.
COMBO = np.array([(a, b) for b in range(52) for a in range(b)], dtype=np.int64)

# ---------------------------------------------------------------- §5.1.1 CANON3

_SUIT_PERMS = list(itertools.permutations(range(4)))


def canonical_form3(hand):
    """Smallest, over all 24 suit permutations, of the (rank, permuted suit) pairs sorted descending."""
    pairs = [(c >> 2, c & 3) for c in hand]
    return min(tuple(sorted(((r, p[s]) for r, s in pairs), reverse=True)) for p in _SUIT_PERMS)


def build_canon3():
    """CANON3[idx3] -> canonical class id in [0, 1755), numbered by ascending canonical form."""
    forms = [canonical_form3(unrank3(i)) for i in range(N3)]
    ids = {f: n for n, f in enumerate(sorted(set(forms)))}
    if len(ids) != N_PRE:
        raise AssertionError(f"expected {N_PRE} canonical classes, got {len(ids)}")
    return np.array([ids[f] for f in forms], dtype=np.uint16)
