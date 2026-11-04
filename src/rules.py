"""酒桌摇骰子（吹牛）规则定义。

规则定稿（2 人各 5 骰，每把独立计分）：
- 普通点数（2-6）3 个起喊（人数+1）；点数 1 是 2 个起喊（人数）。
- 加叫：同个数更高点数，或更高个数任意点数（数量升点数可降）。
- 喊 1 是"重置"：个数至少 ceil(上家个数/2)，每把只能喊一次；
  喊过之后 1 不再百搭、也不能再喊 1。
- 喊完 M个1 后普通点数照常 3 个起（同个数接也能接，1 视为最小点数）。
- "M个1"被开时数实际摇出的 1 的个数。
"""
from dataclasses import dataclass
import math

Bid = tuple  # (count, face)


@dataclass(frozen=True)
class Rules:
    n_players: int = 2
    dice_per_player: int = 5
    min_normal_count: int = 3   # 人数 + 1
    min_one_count: int = 2      # 人数
    one_is_wild: bool = True
    one_bid_once: bool = True   # 喊过 1 不能再喊 1
    one_kills_wild: bool = True  # 喊过 1 后 1 不再百搭

    @property
    def total_dice(self) -> int:
        return self.n_players * self.dice_per_player


DEFAULT_RULES = Rules()


def ceil_half(c: int) -> int:
    """喊 1 的个数下限：上家个数除 2 向上取整。"""
    return -(-c // 2)


def legal_bids(rules: Rules, prev: Bid, one_bid_made: bool) -> list:
    """给定上家叫牌与是否已喊过 1，返回全部合法叫牌。

    prev=None 表示起叫。点数顺序 1 < 2 < ... < 6（1 视为最小，
    但 1 有特殊的"重置"通道）。
    """
    out = []
    max_c = rules.total_dice
    if prev is None:
        for f in range(2, 7):
            out.extend((c, f) for c in range(rules.min_normal_count, max_c + 1))
        if not one_bid_made:
            out.extend((c, 1) for c in range(rules.min_one_count, max_c + 1))
        return out

    c1, f1 = prev
    for f in range(2, 7):
        # 同个数必须点数更高；数量升则点数任意（可降）。
        if f > f1:
            start = max(rules.min_normal_count, c1)
        else:
            start = max(rules.min_normal_count, c1 + 1)
        out.extend((c, f) for c in range(start, max_c + 1))
    if not one_bid_made:
        # 喊 1：至少 ceil(上家个数/2)，也至少 2 个（人数）。
        start = max(rules.min_one_count, ceil_half(c1))
        out.extend((c, 1) for c in range(start, max_c + 1))
    return out


def is_legal(rules: Rules, prev: Bid, one_bid_made: bool, bid: Bid) -> bool:
    return bid in legal_bids(rules, prev, one_bid_made)


def count_true(rules: Rules, all_dice: list, bid: Bid, one_bid_made: bool) -> bool:
    """结算：叫牌是否为真（>= 叫的个数）。

    - 喊 1：数实际摇出的 1 的个数。
    - 百搭期（还没喊过 1）：目标点数 + 1 都算。
    - 斋期（喊过 1）：只数实际目标点数。
    """
    c, f = bid
    if f == 1:
        n = sum(1 for d in all_dice if d == 1)
    else:
        n = sum(1 for d in all_dice if d == f)
        if rules.one_is_wild and rules.one_kills_wild and one_bid_made:
            pass  # 斋期：1 不百搭
        elif rules.one_is_wild:
            n += sum(1 for d in all_dice if d == 1)
    return n >= c


def fmt_bid(bid: Bid) -> str:
    return f"{bid[0]}个{bid[1]}"
