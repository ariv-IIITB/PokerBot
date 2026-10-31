"""Card encoding. card = suit * 13 + rank, rank 0..12 = 2..A, suit 0..3 = c,d,h,s."""
RANKS = "23456789TJQKA"
SUITS = "cdhs"


def parse(s):
    """'Ah' -> int. Accepts upper/lower case."""
    s = s.strip()
    return SUITS.index(s[1].lower()) * 13 + RANKS.index(s[0].upper())


def to_str(c):
    return RANKS[c % 13] + SUITS[c // 13]


def parse_many(seq):
    return tuple(parse(x) for x in seq)


def fmt(cards):
    return " ".join(to_str(c) for c in cards)
