"""人机对战模拟器：在终端里和训练好的策略对打。

用法：python src/play.py

输入格式：
- 叫牌：`3 6` 或 `3个6`（3 个 6）
- 喊1：`h`（自动按规则给出合法个数）
- 开：`k`
- 提示：`?`（显示 P(上家叫牌为真) 和 AI 建议）
- 退出：`q`
"""
import json
import random
import re
import sys

from agents import GreedyAgent, RandomAgent, ThresholdAgent
from belief import p_true
from engine import View, action_key, bucket_of, roll_hand
from rules import DEFAULT_RULES, count_true, fmt_bid, legal_bids

RULES = DEFAULT_RULES


def count_matching(all_dice, bid, one_bid_made):
    """数出符合叫牌的骰子个数（与结算口径一致）。"""
    c, f = bid
    if f == 1:
        return sum(1 for d in all_dice if d == 1)
    n = sum(1 for d in all_dice if d == f)
    if not one_bid_made:
        n += sum(1 for d in all_dice if d == 1)
    return n


def load_params():
    try:
        with open("data/params.json", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def build_ai(level, params):
    """按难度返回 (AI agent, 描述)。"""
    if level == 1:
        return RandomAgent(challenge_prob=0.25, seed=random.randrange(10 ** 6)), \
            "简单：随机乱喊乱开"
    if level == 2:
        return GreedyAgent(), "中等：贪心抬价，几乎不开"
    if level == 3:
        p = params.get("vs_random", {"tau_call": 0.4, "tau_safe": 0.85, "style": "maxp"})
        return ThresholdAgent(p["tau_call"], p["tau_safe"], p["style"]), \
            "困难：训练实战参数（对随机胜率 95.6% 的那个）"
    p = params.get("vs_rational", {"tau_call": 0.4, "tau_safe": 0.75, "style": "maxp"})
    return ThresholdAgent(p["tau_call"], p["tau_safe"], p["style"]), \
        "专家：自我对弈收敛的理论参数（近乎纳什）"


def parse_bid(text):
    m = re.match(r"^(\d+)[\s个*x×]*([1-6])$", text.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def legal_hint(view):
    """给一句人话的合法范围提示。"""
    counts = {}
    for c, f in view.legal:
        counts.setdefault(f, []).append(c)
    parts = []
    for f in sorted(counts):
        cs = counts[f]
        if f == 1:
            parts.append(f"喊1：{min(cs)}个起")
        elif max(cs) - min(cs) == len(cs) - 1:
            parts.append(f"{f}点：{min(cs)}个起")
        else:
            parts.append(f"{f}点：{'/'.join(map(str, cs))}个")
    return "；".join(parts)


class HumanAgent:
    def __init__(self, hints=False):
        self.hints = hints
        self.steps = []

    def choose(self, view):
        print()
        if view.first:
            print("—— 你先手（起叫）——")
        else:
            print(f"—— 上家（对手）叫了 {fmt_bid(view.prev)} ——")
        while True:
            try:
                text = input("你的动作 [如 3 6 / h=喊1 / k=开 / ?=提示 / q=退出] > ")
            except EOFError:
                return ("quit",)
            t = text.strip().lower()
            if t in ("q", "quit", "exit", "退出"):
                return ("quit",)
            if t in ("?", "？"):
                self.show_hint(view)
                continue
            if t in ("k", "开", "o", "open"):
                if view.first:
                    print("起叫不能开，先叫一个。")
                    continue
                return ("challenge",)
            if t in ("h", "喊1", "one"):
                ones = [b for b in view.legal if b[1] == 1]
                if not ones:
                    print("现在不能喊1（已喊过或个数不够）。")
                    continue
                default = min(ones)[0]
                try:
                    s = input(f"喊几个1？可选 {'/'.join(str(c) for c, _ in ones)}"
                              f"，回车={default} > ").strip()
                except EOFError:
                    return ("quit",)
                c = int(s) if s else default
                if (c, 1) not in ones:
                    print(f"{c}个1 不合法。")
                    continue
                return ("bid", (c, 1))
            bid = parse_bid(text)
            if bid is None:
                print("没看懂。示例：`3 6`=3个6，`h`=喊1，`k`=开。")
                continue
            if bid not in view.legal:
                print(f"不合法（{fmt_bid(bid)}）。合法范围：{legal_hint(view)}")
                continue
            return ("bid", bid)

    def show_hint(self, view):
        if view.prev is None:
            p = None
        else:
            p = p_true(view.my_dice, view.prev, view.one_bid_made)
            print(f"P(上家叫牌为真) = {p:.2f}；开的期望分 = {1 - 2 * p:+.2f}")
        advisor = ThresholdAgent(0.4, 0.75, "maxp")
        act = advisor.choose(view)
        if act[0] == "challenge":
            print("AI 建议：开")
        else:
            pp = p_true(view.my_dice, act[1], view.one_bid_made)
            print(f"AI 建议：{fmt_bid(act[1])}（该叫牌为真的概率 {pp:.2f}）")


def show_dice(label, dice):
    print(f"{label}：{' '.join(str(d) for d in dice)}")


def play_one_hand(human, ai, first_is_human, rng):
    dice = roll_hand(RULES, rng)
    my_i, ai_i = (0, 1) if first_is_human else (1, 0)
    views = {my_i: human, ai_i: ai}
    show_dice("你的骰子", dice[my_i])
    print("对手的骰子已摇好（暗）。")
    prev = None
    one_bid_made = False
    turn = my_i if first_is_human else ai_i
    while True:
        legal = tuple(legal_bids(RULES, prev, one_bid_made))
        view = View(my_dice=dice[turn], prev=prev, one_bid_made=one_bid_made,
                    legal=legal, first=(prev is None))
        agent = views[turn]
        if agent is human and human.hints:
            human.show_hint(view)
        action = agent.choose(view)
        if action[0] == "quit":
            return None
        me_turn = (turn == my_i)
        if action[0] == "challenge":
            true = count_true(RULES, dice[0] + dice[1], prev, one_bid_made)
            winner_is_me = (me_turn != true)  # 我开：假则我赢；对手开：真则我输
            n_match = count_matching(dice[0] + dice[1], prev, one_bid_made)
            face_desc = "1" if prev[1] == 1 else (
                f"{prev[1]}（含百搭）" if not one_bid_made else str(prev[1]))
            print(f"\n{'你' if me_turn else '对手'}开！{fmt_bid(prev)} —— "
                  f"数出 {n_match} 个 {face_desc} → 叫牌{'真' if true else '假'}")
            show_dice("你的骰子", dice[my_i])
            show_dice("对手骰子", dice[ai_i])
            print(f"=> {'你' if winner_is_me else '对手'}赢这一把")
            if me_turn:
                human.steps.append({"bucket": bucket_of(view), "action": "开",
                                    "win": winner_is_me})
            return winner_is_me
        bid = action[1]
        if me_turn:
            human.steps.append({"bucket": bucket_of(view),
                                "action": action_key(action), "win": None})
        print(f"{'你' if me_turn else '对手'}叫牌：{fmt_bid(bid)}")
        if bid[1] == 1:
            one_bid_made = True
        prev = bid
        turn = 1 - turn


def main():
    params = load_params()
    print("=== 摇骰子人机对战（2人5骰 · 1百搭 · 喊1重置）===")
    print("难度：1 简单（随机）  2 中等（贪心）  3 困难（实战参数）  4 专家（理论参数）")
    try:
        level = int(input("选难度 [1-4，默认3] > ").strip() or "3")
    except (EOFError, ValueError):
        level = 3
    level = min(max(level, 1), 4)
    ai, desc = build_ai(level, params)
    print(f"已选：{desc}")
    try:
        first = input("谁先手？1=你  2=对手  3=轮流（默认3）> ").strip() or "3"
    except EOFError:
        first = "3"
    try:
        hints = input("开提示模式？y/n（默认n）> ").strip().lower() == "y"
    except EOFError:
        hints = False

    human = HumanAgent(hints=hints)
    rng = random.Random()
    score = {"me": 0, "ai": 0, "n": 0}
    first_is_human = (first == "1")
    print("\n开始对战！每把独立计分。")
    while True:
        print(f"\n===== 第 {score['n'] + 1} 把 | 比分 你 {score['me']} : {score['ai']} =====")
        r = play_one_hand(human, ai, first_is_human, rng)
        if r is None:
            break
        score["n"] += 1
        score["me" if r else "ai"] += 1
        for st in human.steps:
            if st["win"] is None:
                st["win"] = r
        if first == "3":
            first_is_human = not first_is_human
        try:
            s = input("\n回车继续下一把，q 退出 > ").strip().lower()
        except EOFError:
            break
        if s in ("q", "quit", "exit", "退出"):
            break

    print(f"\n===== 对战结束 | 总比分 你 {score['me']} : {score['ai']}（共 {score['n']} 把）=====")
    if score["n"]:
        print(f"你的胜率：{score['me'] / score['n'] * 100:.1f}%")
    stats = {}
    for st in human.steps:
        if st["win"] is None:
            continue
        key = "|".join(st["bucket"])
        d = stats.setdefault(key, {"n": 0, "win": 0})
        d["n"] += 1
        d["win"] += int(st["win"])
    if stats:
        print("\n你的局面表现（胜率最低的 5 个局面）：")
        rows = sorted(stats.items(), key=lambda kv: kv[1]["win"] / kv[1]["n"])
        for key, d in rows[:5]:
            print(f"  {key:24s} {d['win']}/{d['n']} = {d['win'] / d['n'] * 100:.0f}%")
        print("（对照 report/strategy_card.md 里对应行的建议打法复盘）")


if __name__ == "__main__":
    main()
