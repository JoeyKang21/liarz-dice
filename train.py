"""训练：网格搜索 + 自我对弈（迭代最优反应）调参，全程写日志。

产出：
- logs/train_<时间戳>.log   训练全程记录
- out/params.json           最优参数（对随机 / 对理性）
- out/grid_results.json     每轮网格搜索完整得分
"""
import itertools
import json
import logging
import os
import random
import time

from agents import RandomAgent, ThresholdAgent
from engine import play_hand
from rules import DEFAULT_RULES

RULES = DEFAULT_RULES
TAU_CALLS = [0.30, 0.40, 0.50, 0.60]
TAU_SAFES = [0.55, 0.65, 0.75, 0.85]
STYLES = ["maxp", "mincount"]
HANDS_VS_RANDOM = 1200     # 每个配置、每个座位
HANDS_VS_RATIONAL = 800
FP_ROUNDS = 3

log = logging.getLogger("train")


def match_win_rate(agent_a, agent_b, hands, rng):
    """agent_a vs agent_b，两个座位各一半，返回 a 的胜率。"""
    wins = 0
    for seat_a_first in (True, False):
        pair = (agent_a, agent_b) if seat_a_first else (agent_b, agent_a)
        for _ in range(hands // 2):
            winner, _ = play_hand(RULES, pair, rng)
            if (winner == 0) == seat_a_first:
                wins += 1
    return wins / hands


def grid_search(opponent_factory, hands, tag):
    """对给定对手跑全网格，返回 (best_params, results)。"""
    rng = random.Random(20261104)
    results = []
    t0 = time.time()
    for tau_call, tau_safe, style in itertools.product(TAU_CALLS, TAU_SAFES, STYLES):
        agent = ThresholdAgent(tau_call, tau_safe, style)
        wr = match_win_rate(agent, opponent_factory(), hands, rng)
        results.append({"tau_call": tau_call, "tau_safe": tau_safe,
                        "style": style, "win_rate": round(wr, 4)})
        log.info("[%s] tau_call=%.2f tau_safe=%.2f style=%-8s -> 胜率 %.3f",
                 tag, tau_call, tau_safe, style, wr)
    results.sort(key=lambda r: -r["win_rate"])
    best = results[0]
    log.info("[%s] 网格最优: %s  胜率 %.3f  (耗时 %.1fs)",
             tag, {k: best[k] for k in ("tau_call", "tau_safe", "style")},
             best["win_rate"], time.time() - t0)
    return {"tau_call": best["tau_call"], "tau_safe": best["tau_safe"],
            "style": best["style"]}, results


def main():
    os.makedirs("logs", exist_ok=True)
    os.makedirs("out", exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        handlers=[logging.FileHandler(f"logs/train_{ts}.log", encoding="utf-8"),
                  logging.StreamHandler()],
    )
    log.info("=== 开始训练：2人5骰，1百搭，喊1重置规则 ===")
    log.info("网格: tau_call=%s tau_safe=%s style=%s", TAU_CALLS, TAU_SAFES, STYLES)

    # 阶段 1：对随机对手
    log.info("--- 阶段1：网格搜索 vs 随机对手 (%d 手/配置/座位) ---", HANDS_VS_RANDOM)
    best_rand, res_rand = grid_search(
        lambda: RandomAgent(challenge_prob=0.25, seed=7), HANDS_VS_RANDOM, "vs随机")

    # 阶段 2：自我对弈（迭代最优反应 / fictitious play）
    log.info("--- 阶段2：自我对弈 %d 轮迭代最优反应 ---", FP_ROUNDS)
    current = ThresholdAgent(0.45, 0.75, "maxp")
    log.info("初始理性对手 P0: %s", current.params)
    fp_history = []
    for r in range(1, FP_ROUNDS + 1):
        log.info("--- 第 %d 轮：对 P%d 网格搜索最优反应 ---", r, r - 1)
        opp_params = current.params

        def opp_factory(p=opp_params):
            return ThresholdAgent(p["tau_call"], p["tau_safe"], p["style"])

        best_r, res_r = grid_search(opp_factory, HANDS_VS_RATIONAL, f"FP{r}")
        challenger = ThresholdAgent(best_r["tau_call"], best_r["tau_safe"], best_r["style"])
        wr = match_win_rate(challenger, current, 2000, random.Random(99 + r))
        log.info("P%d %s vs P%d %s -> P%d 胜率 %.3f", r, challenger.params, r - 1,
                 current.params, r, wr)
        fp_history.append({"round": r, "challenger": challenger.params,
                           "incumbent": current.params, "challenger_win_rate": round(wr, 4),
                           "grid_top": res_r[:6]})
        current = challenger

    # 最终参数检验
    rng = random.Random(4242)
    final_vs_rand = match_win_rate(current, RandomAgent(challenge_prob=0.25, seed=7),
                                   4000, rng)
    log.info("最终理性策略 %s：对随机对手胜率 %.3f (4000手)", current.params, final_vs_rand)

    params = {
        "vs_random": best_rand,
        "vs_rational": current.params,
        "vs_rational_opponent": fp_history[-1]["incumbent"],  # 最终策略训练时面对的理性对手
        "final_vs_random_winrate": round(final_vs_rand, 4),
    }
    with open("out/params.json", "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)
    with open("out/grid_results.json", "w", encoding="utf-8") as f:
        json.dump({"vs_random": res_rand, "fictitious_play": fp_history}, f,
                  ensure_ascii=False, indent=2)
    log.info("训练完成，参数已写入 out/params.json")


if __name__ == "__main__":
    main()
