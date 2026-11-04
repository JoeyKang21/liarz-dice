"""生成训练报告与策略卡片（Markdown）。

产出：
- report/training_report.md  训练过程与评估结果
- report/strategy_card.md   策略卡片（对随机 / 对理性两版）
"""
import json
import os
from collections import Counter

BUCKET_LABELS = {
    "s>=4": "很强（某点数+百搭 ≥4 个）",
    "s=3": "强（3 个）",
    "s=2": "中（2 个）",
    "s<=1": "弱（≤1 个）",
    "g<=0": "我包得住（差距 ≤0）",
    "g=1": "差 1 个",
    "g=2": "差 2 个",
    "g>=3": "差 3 个以上",
}
ORDER_FIRST = ["s>=4", "s=3", "s=2", "s<=1"]
ORDER_FOLLOW = ["g<=0", "g=1", "g=2", "g>=3"]


def load(name):
    with open(f"data/{name}", encoding="utf-8") as f:
        return json.load(f)


def modal(counter_dict):
    if not counter_dict:
        return "-"
    return Counter(counter_dict).most_common(1)[0][0]


def fmt_pct(x):
    return "-" if x is None else f"{x * 100:.1f}%"


def card_table(stats_buckets, mode, regime, bucket_order):
    rows = []
    for b in bucket_order:
        key = f"{mode}|{regime}|{b}"
        st = stats_buckets.get(key)
        if not st or st["n"] < 30:
            continue
        action = modal(st["actions"])
        bid = modal(st.get("bids_by_action", {}).get(action, {}))
        advice = action if action == "开" else f"{action}（典型：{bid}）"
        rows.append(f"| {BUCKET_LABELS[b]} | {advice} | {fmt_pct(st['win_rate'])} "
                    f"| {st['n']} |")
    if not rows:
        return ""
    header = ("| 局面 | 建议 | 该局面胜率 | 样本数 |\n"
              "|---|---|---|---|")
    return header + "\n" + "\n".join(rows)


def build_card(stats):
    lines = ["# 摇骰子策略卡片（2人5骰 · 1百搭 · 喊1重置）",
             "",
             "用法：先看自己是先手还是后手，按局面行找建议动作；"
             "\"该局面胜率\"是按此策略打、进入该局面后赢下整把的比例（蒙特卡洛 3 万手实测）。",
             "",
             "## 卡片 A：对随机对手（酒桌实战版）",
             "",
             f"整把胜率：**{fmt_pct(stats['random']['win_rate'])}**"
             f"（95% CI {fmt_pct(stats['random']['ci'][0])} – "
             f"{fmt_pct(stats['random']['ci'][1])}）",
             "",
             "### 先手起叫",
             "",
             card_table(stats["random"]["buckets"], "first", "wild", ORDER_FIRST),
             "",
             "### 后手（百搭期，还没人喊 1）",
             "",
             card_table(stats["random"]["buckets"], "follow", "wild", ORDER_FOLLOW),
             "",
             "### 后手（斋期，喊过 1 之后：1 不百搭）",
             "",
             card_table(stats["random"]["buckets"], "follow", "zhai", ORDER_FOLLOW),
             "",
             "## 卡片 B：对理性对手（理论基准版）",
             "",
             f"整把胜率：**{fmt_pct(stats['rational']['win_rate'])}**"
             f"（95% CI {fmt_pct(stats['rational']['ci'][0])} – "
             f"{fmt_pct(stats['rational']['ci'][1])}）",
             "",
             "### 先手起叫",
             "",
             card_table(stats["rational"]["buckets"], "first", "wild", ORDER_FIRST),
             "",
             "### 后手（百搭期）",
             "",
             card_table(stats["rational"]["buckets"], "follow", "wild", ORDER_FOLLOW),
             "",
             "### 后手（斋期）",
             "",
             card_table(stats["rational"]["buckets"], "follow", "zhai", ORDER_FOLLOW),
             "",
             "## 要点",
             "",
             "1. 起叫：手里 1 多（≥2 个）直接喊 2个1，几乎必真、胜率最高；"
             "否则 3 个起喊自己最多的点数。",
             "2. 后手\"包得住\"（差距 ≤0）时别开：继续加叫把压力推回对手，胜率明显更高。",
             "3. 差 3 个以上且 1 还没被喊过：对随机对手直接开（胜率 96%）；"
             "喊 1（个数 = 上家个数÷2 向上取整）是逃生牌，代价是全场进斋、1 不再百搭。",
             "4. 斋期（喊过 1 之后）数字变\"硬\"（只能数实际点数），"
             "差 2 个就别硬抬了，开的性价比上来了。",
             "5. 注：\"该局面胜率\"是进入该局面后按策略打完的整把胜率（含后续影响），"
             "不是单步动作的因果效应。",
             ]
    return "\n".join(lines) + "\n"


def build_report(grid, params, stats):
    lines = ["# 训练报告：摇骰子自我对弈调参",
             "",
             "## 规则",
             "",
             "2 人各 5 骰，每把独立计分（赢记 1 分，目标=单把胜率最大化）；"
             "普通点数 3 个起喊，1 是 2 个起喊；加叫=同个数更高点数或更高个数任意点数；"
             "喊 1 是重置（个数至少 ceil(上家个数/2)），每把只能喊一次，喊过之后 1 不再百搭；"
             "喊 M个1 后普通点数照常 3 个起；\"M个1\"被开时数实际 1 的个数。"
             "5 个数字全不相同为无效手牌：重摇到有效为止，连续 3 次无效直接判负。",
             "",
             "## 方法",
             "",
             "- 解析基线：给定手牌与叫牌，用二项分布精确算 P(叫牌为真)；"
             "策略为参数化阈值（tau_call=开的阈值，tau_safe=叫牌安全线，style=激进/稳健）。",
             "- 调参：网格搜索 4x4x2=32 组参数。",
             "- 对随机对手：直接网格搜索。",
             "- 对理性对手：自我对弈迭代最优反应（fictitious play），3 轮。",
             "- 训练过程全记录：logs/train_*.log。",
             "",
             "## 网格搜索结果（vs 随机对手，前 10）",
             "",
             "| tau_call | tau_safe | style | 胜率 |",
             "|---|---|---|---|"]
    for r in grid["vs_random"][:10]:
        lines.append(f"| {r['tau_call']} | {r['tau_safe']} | {r['style']} "
                     f"| {r['win_rate']:.3f} |")
    lines += ["", "## 自我对弈（迭代最优反应）", "",
              "| 轮次 | 挑战者参数 | 在位者参数 | 挑战者胜率 |",
              "|---|---|---|---|"]
    for h in grid["fictitious_play"]:
        c = h["challenger"]
        i = h["incumbent"]
        lines.append(f"| P{h['round']} | ({c['tau_call']}, {c['tau_safe']}, {c['style']}) "
                     f"| ({i['tau_call']}, {i['tau_safe']}, {i['style']}) "
                     f"| {h['challenger_win_rate']:.3f} |")
    lines += ["",
              "## 最终参数",
              "",
              f"- 对随机对手：{params['vs_random']}",
              f"- 对理性对手：{params['vs_rational']}",
              f"- （训练时面对的理性对手：{params['vs_rational_opponent']}）",
              "",
              "## 评估（各 3 万手，Wilson 95% CI）",
              "",
              "| 对局 | 胜率 | 95% CI |",
              "|---|---|---|"]
    for name in ("random", "rational", "greedy", "mirror"):
        s = stats[name]
        lines.append(f"| {s['desc']} | {s['win_rate']:.3f} "
                     f"| [{s['ci'][0]:.3f}, {s['ci'][1]:.3f}] |")
    lines += ["",
              "注：胜率是相对对手的——对随机对手和对理性对手的最优打法不同，"
              "所以策略卡片分两版。mirror 一栏是理性策略自我对局（应接近 0.5，"
              "用于校验实现对称性）。"]
    return "\n".join(lines) + "\n"


def main():
    os.makedirs("report", exist_ok=True)
    grid = load("grid_results.json")
    params = load("params.json")
    stats = load("stats.json")
    with open("report/strategy_card.md", "w", encoding="utf-8") as f:
        f.write(build_card(stats))
    with open("report/training_report.md", "w", encoding="utf-8") as f:
        f.write(build_report(grid, params, stats))
    print("已生成 report/strategy_card.md 与 report/training_report.md")


if __name__ == "__main__":
    main()
