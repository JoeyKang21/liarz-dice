"""信念层：精确计算"叫牌为真"的概率。

对手手牌先验：均匀摇 5 骰并条件化在"有效手牌"（5 个数字不全相异；
全异要重摇，连续 3 次无效直接判负，所以能进入叫牌阶段的手牌必有效）。
用 6^5 = 7776 全枚举得到精确尾概率，替代二项近似。
"""
from functools import lru_cache
from itertools import product

N = 5

_VALID = [r for r in product(range(1, 7), repeat=N) if len(set(r)) < N]
_DEN = len(_VALID)  # 7056（7776 - 720 个全异手牌）


def _make_tail(hist):
    """尾概率表 t[k] = P(X >= k)。"""
    t = [0.0] * (len(hist) + 2)
    acc = 0.0
    for k in range(len(hist) - 1, -1, -1):
        acc += hist[k] / _DEN
        t[k] = acc
    return t


def _build():
    ones_h = [0] * (N + 1)      # 1 的个数
    face_h = [0] * (N + 1)      # 某非 1 点数的个数（2 代表任意，对称）
    wild_h = [0] * (2 * N + 1)  # 非 1 点数 + 1 的个数（百搭期）
    for r in _VALID:
        c1 = r.count(1)
        cf = r.count(2)
        ones_h[c1] += 1
        face_h[cf] += 1
        wild_h[c1 + cf] += 1
    return _make_tail(ones_h), _make_tail(face_h), _make_tail(wild_h)


_T_ONES, _T_FACE, _T_WILD = _build()


def _tail(t, k):
    if k <= 0:
        return 1.0
    return t[k] if k < len(t) else 0.0


@lru_cache(maxsize=None)
def _p_true_cached(my_sorted: tuple, bid, one_bid_made: bool) -> float:
    c, f = bid
    if f == 1:
        return _tail(_T_ONES, c - my_sorted.count(1))
    if one_bid_made:  # 斋期：1 不百搭
        return _tail(_T_FACE, c - my_sorted.count(f))
    return _tail(_T_WILD, c - my_sorted.count(f) - my_sorted.count(1))


def p_true(my_dice, bid, one_bid_made: bool = False) -> float:
    """P(该叫牌为真 | 我的手牌)。对手手牌按有效手牌条件分布。"""
    return _p_true_cached(tuple(sorted(my_dice)), bid, one_bid_made)
