"""策略：随机 / 贪心 / 阈值（可训练）/ 蒙特卡洛推演。"""
import random

from belief import p_true


class RandomAgent:
    """乱喊乱开：以固定概率开，否则随机合法叫牌。"""
    name = "random"

    def __init__(self, challenge_prob=0.25, seed=None):
        self.challenge_prob = challenge_prob
        self.rng = random.Random(seed)

    def choose(self, view):
        if not view.first and self.rng.random() < self.challenge_prob:
            return ("challenge",)
        return ("bid", self.rng.choice(view.legal))


class GreedyAgent:
    """贪心：永远最小个数抬价（喊自己最稳的点数），只在几乎必假时开。"""
    name = "greedy"

    def choose(self, view):
        if not view.first and p_true(view.my_dice, view.prev, view.one_bid_made) < 0.12:
            return ("challenge",)
        best = min(view.legal,
                   key=lambda b: (b[0], -p_true(view.my_dice, b, view.one_bid_made), b[1]))
        return ("bid", best)


class ThresholdAgent:
    """阈值策略：参数化，用于网格搜索/自我对弈调参。

    - p(上家叫牌为真) < tau_call -> 开
    - 否则在 p(候选叫牌为真) >= tau_safe 的候选里挑：
        style='mincount'：个数最小优先（激进）
        style='maxp'：为真概率最高优先（稳健）
      若没有候选达标，取为真概率最高的候选。
    """
    name = "threshold"

    def __init__(self, tau_call, tau_safe, style="maxp"):
        self.tau_call = tau_call
        self.tau_safe = tau_safe
        self.style = style

    @property
    def params(self):
        return {"tau_call": self.tau_call, "tau_safe": self.tau_safe, "style": self.style}

    def choose(self, view):
        my = view.my_dice
        if not view.first and p_true(my, view.prev, view.one_bid_made) < self.tau_call:
            return ("challenge",)
        scored = [(b, p_true(my, b, view.one_bid_made)) for b in view.legal]
        qual = [x for x in scored if x[1] >= self.tau_safe] or scored
        if self.style == "mincount":
            bid = min(qual, key=lambda x: (x[0][0], -x[1], x[0][1]))[0]
        else:
            bid = min(qual, key=lambda x: (-x[1], x[0][0], x[0][1]))[0]
        return ("bid", bid)


class MCTSAgent:
    """蒙特卡洛推演策略：对每个候选动作模拟对局取平均收益。

    - 对手手牌从"有效手牌条件分布"随机抽样，抽到后整局固定；
    - 展开阶段双方都用阈值策略打到"开"为止；
    - 在接近最优的动作里随机挑（混合策略），避免打法固定被针对。
    """
    name = "mcts"

    def __init__(self, rollouts=60, seed=None, mix_margin=0.03):
        self.rollouts = rollouts
        self.mix_margin = mix_margin
        self.rng = random.Random(seed)
        self._us = ThresholdAgent(0.5, 0.7, "maxp")   # 我方展开策略
        self._opp = ThresholdAgent(0.5, 0.7, "maxp")  # 对手展开模型
        self._valid_hands = None

    def _hands(self):
        if self._valid_hands is None:
            from itertools import product
            self._valid_hands = [r for r in product(range(1, 7), repeat=5)
                                 if len(set(r)) < 5]
        return self._valid_hands

    def _rollout(self, my_dice, opp_dice, prev, one_bid_made, opp_turn):
        """从当前局面推演到一局结束：+1 我赢 / -1 我输。"""
        from engine import View
        from rules import DEFAULT_RULES, count_true, legal_bids
        R = DEFAULT_RULES
        turn = 1 if opp_turn else 0  # 0=我 1=对手
        for _ in range(30):
            legal = tuple(legal_bids(R, prev, one_bid_made))
            dice = my_dice if turn == 0 else opp_dice
            v = View(my_dice=dice, prev=prev, one_bid_made=one_bid_made,
                     legal=legal, first=(prev is None))
            act = (self._us if turn == 0 else self._opp).choose(v)
            if act[0] == "challenge":
                true = count_true(R, list(my_dice) + list(opp_dice), prev,
                                  one_bid_made)
                winner = 1 - turn if true else turn
                return 1.0 if winner == 0 else -1.0
            bid = act[1]
            if bid[1] == 1:
                one_bid_made = True
            prev = bid
            turn = 1 - turn
        return 0.0

    def choose(self, view):
        from rules import DEFAULT_RULES, count_true
        R = DEFAULT_RULES
        cands = []
        if not view.first:
            cands.append(("challenge",))
        by_face = {}
        for b in view.legal:
            by_face.setdefault(b[1], []).append(b)
        for f in sorted(by_face):
            cands.extend(sorted(by_face[f])[:2])  # 每个点数取最小两个个数

        values = {}
        for a in cands:
            total = 0.0
            for _ in range(self.rollouts):
                h = self.rng.choice(self._hands())
                if a[0] == "challenge":
                    true = count_true(R, list(view.my_dice) + list(h),
                                      view.prev, view.one_bid_made)
                    total += -1.0 if true else 1.0
                else:
                    bid = a
                    flag = view.one_bid_made or bid[1] == 1
                    total += self._rollout(view.my_dice, h, bid, flag,
                                           opp_turn=True)
            values[a] = total / self.rollouts

        best = max(values.values())
        pool = [a for a, v in values.items() if v >= best - self.mix_margin]
        pick = self.rng.choice(pool)
        return ("challenge",) if pick[0] == "challenge" else ("bid", pick)
