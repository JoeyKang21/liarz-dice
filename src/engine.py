"""游戏引擎：发牌、叫牌流程、结算、局面分桶。"""
from dataclasses import dataclass

from rules import DEFAULT_RULES, Bid, Rules, is_valid_hand, legal_bids, count_true, fmt_bid


@dataclass(frozen=True)
class View:
    """决策者可见的信息：自己的骰子 + 叫牌历史状态。"""
    my_dice: tuple
    prev: Bid          # None 表示起叫
    one_bid_made: bool
    legal: tuple       # 合法叫牌
    first: bool        # 是否起叫（本手第一个动作）


def roll_hand(rules: Rules, rng):
    """摇牌（2人局规则：全异重摇，连续 rules.strike_limit 次无效判负）。

    返回 (hands, struck)：hands[i] 是玩家 i 最后一次摇的结果，
    struck[i] 表示连续无效判负。
    """
    hands, struck = [], []
    for _ in range(rules.n_players):
        d = None
        for _ in range(rules.strike_limit):
            d = tuple(rng.randint(1, 6) for _ in range(rules.dice_per_player))
            if is_valid_hand(d):
                break
        hands.append(d)
        struck.append(not is_valid_hand(d))
    return hands, struck


def strength_bucket(my_dice) -> str:
    """先手分桶：我最强点数的"有效个数"（百搭期，1 算任何点数）。"""
    ones = my_dice.count(1)
    best = max(my_dice.count(f) + ones for f in range(2, 7))
    if best >= 4:
        return "s>=4"
    if best == 3:
        return "s=3"
    if best == 2:
        return "s=2"
    return "s<=1"


def gap_bucket(my_dice, bid: Bid, one_bid_made: bool) -> str:
    """后手分桶：上家叫牌离我"包得住"的水平差几个。"""
    c, f = bid
    if f == 1:
        eff = my_dice.count(1)
    else:
        eff = my_dice.count(f) + (0 if one_bid_made else my_dice.count(1))
    gap = c - eff
    if gap <= 0:
        return "g<=0"
    if gap == 1:
        return "g=1"
    if gap == 2:
        return "g=2"
    return "g>=3"


def bucket_of(view: View) -> tuple:
    """局面分桶键：(mode, regime, bucket)。"""
    if view.first:
        return ("first", "wild", strength_bucket(view.my_dice))
    regime = "zhai" if view.one_bid_made else "wild"
    return ("follow", regime, gap_bucket(view.my_dice, view.prev, view.one_bid_made))


def action_key(action) -> str:
    """动作类别：开 / 喊1 / 加叫。"""
    if action[0] == "challenge":
        return "开"
    return "喊1" if action[1][1] == 1 else "加叫"


def play_hand(rules: Rules, agents, rng):
    """跑一整把，返回 (赢家 index, trace)。agent0 先手叫牌。

    连续 3 次无效手牌直接判负（trace 为空）；双方都判负则重开一把。
    """
    while True:
        dice, struck = roll_hand(rules, rng)
        if not any(struck):
            break
        if all(struck):
            continue
        return 1 - struck.index(True), []  # 判负者输
    prev = None
    one_bid_made = False
    turn = 0
    trace = []
    for _ in range(200):
        my = dice[turn]
        legal = tuple(legal_bids(rules, prev, one_bid_made))
        view = View(my_dice=my, prev=prev, one_bid_made=one_bid_made,
                    legal=legal, first=(prev is None))
        action = agents[turn].choose(view)
        if action[0] == "challenge":
            if prev is None:
                raise RuntimeError("起叫不能开")
            true = count_true(rules, dice[0] + dice[1], prev, one_bid_made)
            winner = 1 - turn if true else turn  # 叫牌为真 -> 叫牌者赢
            trace.append({"player": turn, "bucket": bucket_of(view),
                          "action": "开", "bid": None, "win": winner == turn})
            return winner, trace
        bid = action[1]
        if bid not in legal:
            raise RuntimeError(f"非法叫牌 {fmt_bid(bid)} prev={prev} one={one_bid_made}")
        trace.append({"player": turn, "bucket": bucket_of(view),
                      "action": action_key(action), "bid": fmt_bid(bid),
                      "win": None})
        if bid[1] == 1:
            one_bid_made = True
        prev = bid
        turn = 1 - turn
    raise RuntimeError("叫牌循环超时")
