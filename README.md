# Liarz Dice

酒桌摇骰子（吹牛）策略模拟器：自我对弈训练，输出"什么情况下喊什么、胜率最高"的策略卡片。

## 规则（2人5骰）

- 每把独立计分，赢记 1 分（目标 = 单把胜率最大化）
- 普通点数（2-6）3 个起喊（人数+1）；点数 1 是 2 个起喊（人数）
- 加叫：同个数更高点数，或更高个数任意点数
- 喊 1 是"重置"：个数至少 ceil(上家个数/2)，每把只能喊一次；喊过之后 1 不再百搭、不能再喊 1
- 喊 M个1 后普通点数照常 3 个起
- "M个1"被开时数实际摇出的 1 的个数
- 5 个数字全不相同为无效手牌：2 人局重摇到有效为止，连续 3 次无效直接判负（非单挑局算 0 个骰子）

## 用法

```bash
python src/play.py        # 人机对战（4 档难度，输入 ? 可开提示）
python src/train.py       # 网格搜索 + 自我对弈调参（日志写入 logs/）
python src/evaluate.py    # 3 万手蒙特卡洛评估（结果写入 data/stats.json）
python src/make_card.py   # 生成 report/strategy_card.md 与 training_report.md
```

## 目录

| 路径 | 内容 |
|---|---|
| `src/rules.py` | 规则定义、合法叫牌、结算口径 |
| `src/belief.py` | 贝叶斯基线：精确计算 P(叫牌为真) |
| `src/engine.py` | 发牌、叫牌流程、局面分桶 |
| `src/agents.py` | 随机 / 贪心 / 阈值（可训练）策略 |
| `src/train.py` | 训练：网格搜索 + 迭代最优反应自我对弈 |
| `src/evaluate.py` | 蒙特卡洛评估（胜率 + Wilson CI + 分桶统计） |
| `src/make_card.py` | 生成训练报告与策略卡片 |
| `src/play.py` | 人机对战模拟器（简单/中等/困难/专家 4 档） |
| `data/` | 训练/评估中间产物（params、grid、stats JSON） |
| `logs/` | 训练全程日志 |
| `report/` | 策略卡片与训练报告 |
| `docs/` | 规则文档（含 2025 初版规则草案） |

## License

[MIT](LICENSE)
