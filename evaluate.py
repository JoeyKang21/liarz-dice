"""评估：大规模蒙特卡洛对局，统计胜率（含置信区间）与分桶胜率。

产出 out/stats_<对手>.json，供 make_card.py 生成策略卡片。
"""
import json
import logging
import math
import os
import random
import time
from collections import Counter, defaultdict

from agents import GreedyAgent, RandomAgent, ThresholdAgent
from engine import play_hand
from rules import DEFAULT_RULES

RULES = DEFAULT_RULES
HANDS = 30000


def wilson_ci(wins, n, z=1.96):
    """胜率的 Wilson 95% 置信区间。"""
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (p, max(0.0, center - half), min(1.0, center + half))


def run_match(agent_a, agent_b, hands, rng):
    """跑 hands 把，返回 (a 胜场, 分桶统计)。两个座位各一半。"""
    wins = 0
    buckets = defaultdict(lambda: {"n": 0, "win": 0,
                                   "actions": Counter(), "bids": defaultdict(Counter)})
    for seat_a_first in (True, False):
        pair = (agent_a, agent_b) if seat_a_first else (agent_b, agent_a)
        for _ in range(hands // 2):
            winner, trace = play_hand(RULES, pair, rng)
            a_won = (winner == 0) == seat_a_first
            if a_won:
                wins += 1
            for step in trace:
                if step["player"] != (0 if seat_a_first else 1):
                    continue  # 只统计 agent_a 的决策点
                key = "|".join(step["bucket"])
                st = buckets[key]
                st["n"] += 1
                st["win"] += int(a_won)
                st["actions"][step["action"]] += 1
                if step["bid"]:
                    st["bids"][step["action"]][step["bid"]] += 1
    return wins, buckets


def serialize(buckets):
    out = {}
    for key, st in buckets.items():
        out[key] = {
            "n": st["n"],
            "win": st["win"],
            "win_rate": round(st["win"] / st["n"], 4) if st["n"] else None,
            "actions": dict(st["actions"]),
            "bids_by_action": {a: dict(c.most_common(5))
                               for a, c in st["bids"].items()},
        }
    return out


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    os.makedirs("out", exist_ok=True)
    with open("out/params.json", encoding="utf-8") as f:
        params = json.load(f)

    policy_rand = ThresholdAgent(**params["vs_random"])
    policy_rat = ThresholdAgent(**params["vs_rational"])
    opp_rat = ThresholdAgent(**params["vs_rational_opponent"])

    matchups = [
        ("random", policy_rand, RandomAgent(challenge_prob=0.25, seed=7),
         "策略卡片 A：对随机对手"),
        ("rational", policy_rat, opp_rat, "策略卡片 B：对理性对手"),
        ("greedy", policy_rand, GreedyAgent(), "参考：对贪心对手"),
        ("mirror", policy_rat, ThresholdAgent(**params["vs_rational"]),
         "参考：理性策略自我对局"),
    ]
    results = {}
    for name, me, opp, desc in matchups:
        t0 = time.time()
        wins, buckets = run_match(me, opp, HANDS, random.Random(31337))
        p, lo, hi = wilson_ci(wins, HANDS)
        logging.info("%s：胜率 %.3f [%.3f, %.3f] (%d 手, %.0fs)",
                     desc, p, lo, hi, HANDS, time.time() - t0)
        results[name] = {
            "desc": desc, "hands": HANDS,
            "win_rate": round(p, 4), "ci": [round(lo, 4), round(hi, 4)],
            "buckets": serialize(buckets),
        }
    with open("out/stats.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logging.info("评估完成，写入 out/stats.json")


if __name__ == "__main__":
    main()
