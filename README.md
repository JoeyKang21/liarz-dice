# Liarz Dice

酒桌摇骰子（吹牛）策略模拟器：自我对弈训练，输出"什么情况下喊什么、胜率最高"的策略卡片。

## 规则（2人5骰）

- 每把独立计分，赢记 1 分（目标 = 单把胜率最大化）
- 普通点数（2-6）3 个起喊（人数+1）；点数 1 是 2 个起喊（人数）
- 加叫：同个数更高点数，或更高个数任意点数
- 喊 1 是"重置"：个数至少 ceil(上家个数/2)，每把只能喊一次；喊过之后 1 不再百搭、不能再喊 1
- 喊 M个1 后普通点数照常 3 个起
- "M个1"被开时数实际摇出的 1 的个数

## 用法

```bash
python train.py       # 网格搜索 + 自我对弈调参（日志写入 logs/）
python evaluate.py    # 3 万手蒙特卡洛评估（结果写入 out/stats.json）
python make_card.py   # 生成 report/strategy_card.md 与 training_report.md
```

## 结构

| 文件 | 内容 |
|---|---|
| `rules.py` | 规则定义、合法叫牌、结算口径 |
| `belief.py` | 贝叶斯基线：精确计算 P(叫牌为真) |
| `engine.py` | 发牌、叫牌流程、局面分桶 |
| `agents.py` | 随机 / 贪心 / 阈值（可训练）策略 |
| `train.py` | 训练：网格搜索 + 迭代最优反应自我对弈 |
| `evaluate.py` | 蒙特卡洛评估（胜率 + Wilson CI + 分桶统计） |
| `make_card.py` | 生成训练报告与策略卡片 |

## License

[MIT](LICENSE)
