"""复盘分析：读取 play.py 记录的对局（logs/games_*.jsonl），分析打法与输赢模式。

用法：python src/analyze_games.py [对局文件]
"""
import glob
import json
import sys

from belief import p_true
from engine import gap_bucket, strength_bucket
from rules import DEFAULT_RULES, fmt_bid, legal_bids

RULES = DEFAULT_RULES

# 局面记号 -> 明文
LABELS = {
    "s<=1": "牌很弱(最强不到2个)",
    "s=2": "牌弱(最强2个)",
    "s=3": "牌中(最强3个)",
    "s>=4": "牌强(最强4个以上)",
    "g<=0": "自己就够数",
    "g=1": "差1个",
    "g=2": "差2个",
    "g>=3": "差3个以上",
}


def pretty(key: str) -> str:
    head, _, tag = key.partition("|")
    return f"{head}·{LABELS.get(tag, tag)}"


def load_latest():
    files = sorted(glob.glob("logs/games_*.jsonl"))
    if not files:
        print("没找到对局记录（logs/games_*.jsonl）。先用 python src/play.py 打几把。")
        sys.exit(0)
    path = sys.argv[1] if len(sys.argv) > 1 else files[-1]
    hands = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                hands.append(json.loads(line))
    return path, hands


def main():
    path, hands = load_latest()
    done = [h for h in hands if h["winner"] in ("me", "ai")]
    print(f"对局文件：{path}   共 {len(hands)} 条记录，有效 {len(done)} 把\n")

    if done:
        wins = sum(1 for h in done if h["winner"] == "me")
        print(f"总胜率：{wins}/{len(done)} = {wins / len(done) * 100:.1f}%\n")

    opens = {"me": [0, 0], "ai": [0, 0]}     # [次数, 赢]
    bluffs = [0, 0]                          # [我的 bluff 叫牌数, 我的总叫牌数]
    buckets = {}
    lose_buckets = {}
    for h in done:
        prev = None
        my_last_key = None
        for st in h["steps"]:
            if st.get("act") == "strike":
                continue
            if st["who"] == "me":
                my = tuple(h["my_dice"])
                if prev is None:
                    key = "起叫|" + strength_bucket(my)
                else:
                    key = "后手|" + gap_bucket(my, tuple(prev), st["one_bid_made"])
                my_last_key = key
                d = buckets.setdefault(key, {"n": 0, "win": 0})
                d["n"] += 1
                d["win"] += int(h["winner"] == "me")
                if st["act"] == "bid":
                    bluffs[1] += 1
                    if p_true(my, tuple(st["bid"]), st["one_bid_made"]) < 0.5:
                        bluffs[0] += 1
            if st["act"] == "open":
                opens[st["who"]][0] += 1
                opens[st["who"]][1] += int(h["winner"] == st["who"])
            prev = st["bid"]
        if h["winner"] == "ai" and my_last_key:
            lose_buckets[my_last_key] = lose_buckets.get(my_last_key, 0) + 1

    print("开盅统计（开对了才赢）：")
    for who, label in (("me", "你"), ("ai", "对手")):
        n, w = opens[who]
        rate = f"{w / n * 100:.0f}%" if n else "-"
        print(f"  {label}：开了 {n} 次，成功率 {rate}")
    if bluffs[1]:
        print(f"\n你的叫牌风险：P(真)<0.5 的叫牌占 {bluffs[0]}/{bluffs[1]} "
              f"= {bluffs[0] / bluffs[1] * 100:.0f}%（虚张声势比例）")

    if buckets:
        print("\n你的局面胜率（你每次出手时的局面 → 这把最终胜率）：")
        for key, d in sorted(buckets.items(), key=lambda kv: kv[1]["win"] / kv[1]["n"]):
            print(f"  {pretty(key):28s} {d['win'] / d['n'] * 100:3.0f}%  ({d['win']}/{d['n']})")
    if lose_buckets:
        print("\n你输掉的把，最后一次出手时的局面：")
        for key, n in sorted(lose_buckets.items(), key=lambda kv: -kv[1]):
            print(f"  {pretty(key):28s} {n} 把")

    by_diff = {}
    for h in done:
        d = by_diff.setdefault(h["difficulty"], {"n": 0, "win": 0})
        d["n"] += 1
        d["win"] += int(h["winner"] == "me")
    if len(by_diff) > 1:
        print("\n按难度：")
        for lv in sorted(by_diff):
            d = by_diff[lv]
            print(f"  难度{lv}：{d['win']}/{d['n']} = {d['win'] / d['n'] * 100:.0f}%")


if __name__ == "__main__":
    main()
