"""信念层：精确计算"叫牌为真"的概率（对手 5 骰独立均匀）。"""
import math
from functools import lru_cache

from rules import DEFAULT_RULES, Bid

N = DEFAULT_RULES.dice_per_player


@lru_cache(maxsize=None)
def binom_tail(n: int, p: float, k: int) -> float:
    """P(X >= k), X ~ Bin(n, p)。"""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


@lru_cache(maxsize=None)
def _p_true_cached(my_sorted: tuple, bid: Bid, one_bid_made: bool) -> float:
    c, f = bid
    if f == 1:
        mine = my_sorted.count(1)
        return binom_tail(N, 1 / 6, c - mine)
    mine = my_sorted.count(f)
    if one_bid_made:  # 斋期：1 不百搭
        return binom_tail(N, 1 / 6, c - mine)
    mine += my_sorted.count(1)  # 百搭期：1 算任何点数
    return binom_tail(N, 2 / 6, c - mine)


def p_true(my_dice, bid: Bid, one_bid_made: bool = False) -> float:
    """P(该叫牌为真 | 我的手牌)。对手骰子按独立均匀先验。"""
    return _p_true_cached(tuple(sorted(my_dice)), bid, one_bid_made)
