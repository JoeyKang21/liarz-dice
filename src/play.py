"""人机对战模拟器：在终端里和训练好的策略对打。

用法：python src/play.py

输入格式：
- 叫牌：`3 6` 或 `3个6`（3 个 6）
- 喊1：`h`（自动按规则给出合法个数）
- 开：`k`
- 提示：`?`
- 退出：`q`
"""
import json
import os
import random
import re
import sys
import time

from agents import GreedyAgent, MCTSAgent, RandomAgent, ThresholdAgent
from belief import p_true
from engine import View, action_key, bucket_of
from rules import DEFAULT_RULES, count_true, fmt_bid, is_valid_hand, legal_bids

RULES = DEFAULT_RULES
RULE_LINE = "─" * 46


def enable_ansi():
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(h, ctypes.byref(mode)):
            k32.SetConsoleMode(h, mode.value | 0x0004)
    except Exception:
        pass


enable_ansi()
USE_COLOR = sys.stdout.isatty()


def c(s, code):
    return f"\033[{code}m{s}\033[0m" if USE_COLOR else s


def bold(s):
    return c(s, "1")


def dim(s):
    return c(s, "2")


def green(s):
    return c(s, "32")


def red(s):
    return c(s, "31")


def yellow(s):
    return c(s, "33")


def fmt_dice(dice, hidden=False):
    if hidden:
        return " ".join("●" for _ in dice)
    return " ".join(str(d) for d in dice)


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
            "简单 · 随机乱喊"
    if level == 2:
        return GreedyAgent(), "中等 · 贪心抬价"
    if level == 3:
        p = params.get("vs_random", {"tau_call": 0.3, "tau_safe": 0.85, "style": "maxp"})
        return ThresholdAgent(p["tau_call"], p["tau_safe"], p["style"]), \
            "困难 · 训练实战参数"
    p = params.get("vs_rational", {"tau_call": 0.3, "tau_safe": 0.55, "style": "maxp"})
    return MCTSAgent(rollouts=100, seed=random.randrange(10 ** 6)), \
        "专家 · 蒙特卡洛推演"


def parse_bid(text):
    m = re.match(r"^(\d+)[\s个*x×]*([1-6])$", text.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def legal_hint(view):
    counts = {}
    for cc, f in view.legal:
        counts.setdefault(f, []).append(cc)
    parts = []
    for f in sorted(counts):
        cs = counts[f]
        if f == 1:
            parts.append(f"喊1 {min(cs)}个起")
        elif max(cs) - min(cs) == len(cs) - 1:
            parts.append(f"{f}点 {min(cs)}个起")
        else:
            parts.append(f"{f}点 {'/'.join(map(str, cs))}个")
    return " | ".join(parts)


class HumanAgent:
    def __init__(self, hints=False):
        self.hints = hints
        self.steps = []

    def choose(self, view):
        while True:
            try:
                text = input(yellow("你 > ")).strip()
            except EOFError:
                return ("quit",)
            t = text.lower()
            if t in ("q", "quit", "exit", "退出"):
                return ("quit",)
            if t in ("?", "？"):
                self.show_hint(view)
                continue
            if t in ("k", "开", "o", "open"):
                if view.first:
                    print(dim("  起叫不能开"))
                    continue
                return ("challenge",)
            if t in ("h", "喊1", "one"):
                ones = [b for b in view.legal if b[1] == 1]
                if not ones:
                    print(dim("  现在不能喊1"))
                    continue
                default = min(ones)[0]
                try:
                    s = input(f"喊几个1？{'/'.join(str(x) for x, _ in ones)}"
                              f"，回车={default} > ").strip()
                except EOFError:
                    return ("quit",)
                cc = int(s) if s else default
                if (cc, 1) not in ones:
                    print(dim(f"  {cc}个1 不合法"))
                    continue
                return ("bid", (cc, 1))
            bid = parse_bid(text)
            if bid is None:
                print(dim("  没看懂 · `3 6`=3个6  `h`=喊1  `k`=开  `?`=提示"))
                continue
            if bid not in view.legal:
                print(dim(f"  {fmt_bid(bid)} 不合法 → {legal_hint(view)}"))
                continue
            return ("bid", bid)

    def show_hint(self, view):
        if view.prev is not None:
            p = p_true(view.my_dice, view.prev, view.one_bid_made)
            line = f"P(真)={p:.2f}   开的期望={1 - 2 * p:+.2f}"
        else:
            line = "起叫局面"
        act = ThresholdAgent(0.3, 0.55, "maxp").choose(view)
        if act[0] == "challenge":
            line += "   AI建议：开"
        else:
            pp = p_true(view.my_dice, act[1], view.one_bid_made)
            line += f"   AI建议：{fmt_bid(act[1])} (P={pp:.2f})"
        print(dim("  " + line))


def roll_with_display(hands, struck, idx, who, rng):
    for k in range(1, RULES.strike_limit + 1):
        d = tuple(rng.randint(1, 6) for _ in range(RULES.dice_per_player))
        if is_valid_hand(d):
            hands[idx] = d
            struck[idx] = False
            return
        print(f"  {who} {fmt_dice(d)} {dim(f'全异，重摇 {k}/{RULES.strike_limit}')}")
    hands[idx] = d
    struck[idx] = True


def play_one_hand(human, ai, first_is_human, rng, record=None):
    def rec(**kw):
        if record is not None:
            record["steps"].append(kw)

    my_i, ai_i = (0, 1) if first_is_human else (1, 0)
    while True:
        hands, struck = [None, None], [False, False]
        roll_with_display(hands, struck, my_i, "你", rng)
        roll_with_display(hands, struck, ai_i, "对手", rng)
        if all(struck):
            print(dim("  双方连续无效，重开一把"))
            continue
        break
    if record is not None:
        record["my_dice"] = list(hands[my_i])
        record["ai_dice"] = list(hands[ai_i])
    if any(struck):
        loser = struck.index(True)
        winner_is_me = (loser == ai_i)
        print(f"  你的骰子  {fmt_dice(hands[my_i])}")
        print(f"  对手骰子  {fmt_dice(hands[ai_i])}")
        who = "对手" if loser == ai_i else "你"
        print(f"  {red(who)} 连续 3 次无效判负 → "
              f"{green('你赢') if winner_is_me else red('对手赢')}")
        rec(who="system", act="strike", detail=who)
        return winner_is_me

    dice = hands
    print(f"  你的骰子  {bold(fmt_dice(dice[my_i]))}")
    print(f"  对手骰子  {fmt_dice(dice[ai_i], hidden=True)}")
    print()

    history = []
    prev = None
    one_bid_made = False
    turn = my_i if first_is_human else ai_i
    views = {my_i: human, ai_i: ai}
    while True:
        legal = tuple(legal_bids(RULES, prev, one_bid_made))
        view = View(my_dice=dice[turn], prev=prev, one_bid_made=one_bid_made,
                    legal=legal, first=(prev is None))
        me_turn = (turn == my_i)
        if history:
            print(f"  叫牌  {' → '.join(history)}")
        print(f"  轮到{'你' if me_turn else '对手'}" +
              ("（起叫）" if view.first else ""))
        agent = views[turn]
        if agent is human and human.hints:
            human.show_hint(view)
        action = agent.choose(view)
        if action[0] == "quit":
            return None
        rec(who="me" if me_turn else "ai",
            act="open" if action[0] == "challenge" else "bid",
            bid=list(action[1]) if action[0] == "bid" else list(view.prev),
            one_bid_made=view.one_bid_made)
        if action[0] == "challenge":
            true = count_true(RULES, dice[0] + dice[1], prev, one_bid_made)
            winner_is_me = (me_turn != true)
            n_match = 0
            for d in dice[0] + dice[1]:
                if d == prev[1] or (prev[1] != 1 and not one_bid_made and d == 1):
                    n_match += 1
            face_desc = "1" if prev[1] == 1 else (
                f"{prev[1]}(含百搭)" if not one_bid_made else str(prev[1]))
            print(f"\n  {'你' if me_turn else '对手'}开！{fmt_bid(prev)}"
                  f" —— 数出 {n_match} 个 {face_desc} → "
                  f"{green('真') if true else red('假')}")
            print(f"  你的骰子  {fmt_dice(dice[my_i])}")
            print(f"  对手骰子  {fmt_dice(dice[ai_i])}")
            print(f"  {green('★ 你赢这把') if winner_is_me else red('★ 对手赢这把')}")
            if me_turn:
                human.steps.append({"bucket": bucket_of(view), "action": "开",
                                    "win": winner_is_me})
            return winner_is_me
        bid = action[1]
        if me_turn:
            human.steps.append({"bucket": bucket_of(view),
                                "action": action_key(action), "win": None})
        history.append(f"{'你' if me_turn else '对手'} {fmt_bid(bid)}")
        if bid[1] == 1:
            one_bid_made = True
        prev = bid
        turn = 1 - turn
        print()


def main():
    params = load_params()
    print(bold("\n摇骰子 · 人机对战") + dim("  （2人5骰 · 1百搭 · 喊1重置 · 全异重摇）"))
    print(dim("命令：`3 6`=叫3个6 · `h`=喊1 · `k`=开 · `?`=提示 · `q`=退出\n"))
    print("难度  1 简单   2 中等   3 困难   4 专家")
    try:
        level = int(input("选难度 [回车=3] > ").strip() or "3")
    except (EOFError, ValueError):
        level = 3
    level = min(max(level, 1), 4)
    ai, desc = build_ai(level, params)
    try:
        first = input("先手   1 你   2 对手   3 轮流 [回车=3] > ").strip() or "3"
    except EOFError:
        first = "3"
    try:
        hints = input("提示模式 y/n [回车=n] > ").strip().lower() == "y"
    except EOFError:
        hints = False

    human = HumanAgent(hints=hints)
    rng = random.Random()
    score = {"me": 0, "ai": 0, "n": 0}
    first_is_human = (first == "1")
    os.makedirs("logs", exist_ok=True)
    game_log_path = f"logs/games_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    print(f"\n{bold('开战')}  对手：{desc}  {dim(f'对局记录 → {game_log_path}')}")
    while True:
        score_line = f"你 {score['me']} : {score['ai']} 对手"
        print(f"\n{RULE_LINE}")
        print(f" 第 {score['n'] + 1} 把    {bold(score_line)}")
        print(RULE_LINE)
        record = {"hand": score["n"] + 1, "difficulty": level,
                  "first": "me" if first_is_human else "ai", "steps": []}
        r = play_one_hand(human, ai, first_is_human, rng, record)
        record["winner"] = "quit" if r is None else ("me" if r else "ai")
        with open(game_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
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
            s = input(dim("\n回车继续 · q 退出 > ")).strip().lower()
        except EOFError:
            break
        if s in ("q", "quit", "exit", "退出"):
            break

    score_line = f"你 {score['me']} : {score['ai']} 对手"
    print(f"\n{RULE_LINE}")
    print(f" 结束    {bold(score_line)}    共 {score['n']} 把")
    if score["n"]:
        print(f" 你的胜率  {score['me'] / score['n'] * 100:.1f}%")
    stats = {}
    for st in human.steps:
        if st["win"] is None:
            continue
        key = "|".join(st["bucket"])
        d = stats.setdefault(key, {"n": 0, "win": 0})
        d["n"] += 1
        d["win"] += int(st["win"])
    if stats:
        print(dim("\n你的弱项局面（胜率最低 5 个）："))
        rows = sorted(stats.items(), key=lambda kv: kv[1]["win"] / kv[1]["n"])
        for key, d in rows[:5]:
            rate = d["win"] / d["n"] * 100
            print(f"  {key:22s} {rate:3.0f}%  ({d['win']}/{d['n']})")
        print(dim("对照 report/strategy_card.md 复盘"))
    print(RULE_LINE)


if __name__ == "__main__":
    main()
