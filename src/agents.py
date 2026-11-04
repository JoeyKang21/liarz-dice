"""策略：随机 / 贪心 / 阈值（可训练）。"""
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
