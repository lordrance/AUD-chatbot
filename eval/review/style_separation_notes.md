# 风格分离（warm vs neutral）— 评审与改 prompt 备忘

## 操纵意图（与导师框架一致）

- **唯一主操纵**：关系/语气风格（warm vs neutral）。
- **必须对齐**：长度习惯、阶段顺序、策略库、安全规则、模型与解码；避免变成「好 bot vs 差 bot」。

## warm（empathic）应出现的信号

- 用户具体内容被**简短接住**（反映的是用户说的场景，而非泛泛「我理解你」）。
- **每轮最多**一句轻量反映或肯定；**不**堆叠多种反映。
- **协作式**邀请下一步，而非审问清单感。

## neutral 应出现的信号

- **Recap → 单一问题**：先一句客观复述用户刚给的事实，再一个明确问题。
- **无** cheerleading（「你真棒」「坚持下去」类）。
- **无** 强关系性语言（心疼、抱抱、陪你哭）。
- 仍保持 **respectful、clear、structured**；避免「因中立而冷漠或命令式」。

## 易混淆点（评审时重点盯）

| 现象 | 更可能的问题 |
|------|----------------|
| neutral 出现「特别理解你的感受」 | **风格泄漏** → 检查是否误用 warm 句式 |
| warm 只有冷 recap、无一点温度 | **操纵不足** → 可略增反映，但仍控 1 句 |
| 两臂使用同一长模板，仅换开头两字 | **脚本感** → 阶段 YAML / style_contract 需强调差异化结构 |
| neutral 连续多轮无 recap | **不符合 neutral 契约** → 强调「先复述再发问」 |

## v0.2 prompt 中对应位置

- 臂级差异：`prompts/warm.yaml`、`prompts/neutral.yaml` 内 `style_contract`、`tone_do` / `tone_avoid`。
- 阶段级微调：`stage_*` 中 `stage_hint` 与槽位问句（控制一问一答与 Stage 3 具体度）。
