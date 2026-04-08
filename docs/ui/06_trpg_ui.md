# 06 — TRPG 互动模式专属 UI

> **Step 6.6** | TRPG 互动会话界面
>
> 核心后端模块：`agents/interactive.py`
>
> 关键类：`InteractiveAgent` · `InteractiveSession` · `SessionPhase` · `DecisionPoint`

---

## 1. TRPG 模式激活

用户在顶部导航栏切换模式选择器：

```
[✍️ 标准生成模式]  |  [🎲 TRPG 互动模式 ← 当前]  |  [🔧 Agent 车间]
```

进入 TRPG 模式后，界面替换为专属的"PING_PONG 双屏面板"。

---

## 2. 主界面：PING_PONG 双屏面板

**后端映射**：`InteractiveAgent.start()` / `.step()` / `InteractiveSession.phase`

```
┌── TRPG PING_PONG 面板 ─────────────────────────────────────────────────────┐
│                                                                             │
│  ┌── DM 区（左60%）──────────────────┐  ┌── 玩家区（右40%）──────────────┐  │
│  │                                  │  │                                │  │
│  │  [Session 状态灯] PING_PONG ●     │  │  [玩家行动输入框]               │  │
│  │                                  │  │  ____________________________  │  │
│  │  [DM 叙事流（打字机效果）]          │  │                                │  │
│  │  "黑夜降临，你站在永夜山脉入口，    │  │  [A] 谨慎探查周围环境           │  │
│  │   寒风裹挟着血腥气息袭来……"        │  │  [B] 快速穿越关卡              │  │
│  │                                  │  │  [C] 原地等待伙伴               │  │
│  │  ─────────────────────────────  │  │                                │  │
│  │  [选项 A]：谨慎探查周围环境         │  │  [手动输入行动]          [发送]  │  │
│  │  [选项 B]：快速穿越关卡             │  │                                │  │
│  │  [选项 C]：原地等待伙伴             │  │  决策密度指示条（见 §3）         │  │
│  │                                  │  │  历史记录 ↑                    │  │
│  └──────────────────────────────────┘  └────────────────────────────────┘  │
│                                                                             │
│  底部工具栏：[ROLLBACK] [INTERRUPT] [帮回快捷按钮组] [结束会话]                │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.1 DM 区（左 60%）

- 叙事文本：打字机效果（35ms/字），来自 `InteractiveAgent.step()` 返回
- 边框：`SessionPhase` 状态联动颜色（见 §2.3）
- 选项高亮：`DecisionPoint.options` 中每个选项一行，格式 `[选项 X]：描述`
- DM 绝不替玩家做决定（`anti_proxy_rule`）：若 AI 生成内容中含替代玩家选择的文字，红色警告线标注

### 2.2 玩家区（右 40%）

- 选项按钮：自动映射 `DecisionPoint.options`（最多 6 个）
- 手动输入框：允许玩家自由行动（非选项行动）
- 历史记录：可上下滚动查看本 session 所有 `TurnRecord`

### 2.3 SessionPhase 状态颜色映射

**后端来源**：`agents/interactive.py · SessionPhase` 枚举

| `SessionPhase` | 面板左边框颜色 | 状态灯文字 |
|----------------|-------------|---------|
| `INIT` | `#999999` | 初始化 |
| `OPENING` | `#2ef2ff` 呼吸 | 开场白 |
| `PING_PONG` | `#2ef2ff` 长亮 | 对话进行中 |
| `ROLLBACK` | `#f5a623` | 时间回溯中 |
| `INTERRUPT` | `#ff2e88` | 帮回介入 |
| `PACING_ALERT` | `#ff4040` 闪烁 | 节奏预警 |
| `LANDING` | `#3f5a48` | 着陆收束 |
| `MAINTENANCE` | `#3f5a48` 慢呼吸 | 章末维护 |
| `ENDED` | `#999999` | 会话已结束 |

---

## 3. 决策密度指示条（Decision Density Indicator）

**后端映射**：`agents/interactive.py · DecisionDensity` · `_DENSITY_LIMITS`  
限制值：`dense=150` / `normal=300` / `sparse=800` 字符

```
玩家区底部：

  [🔴 密集] ●──────────────────────── [🟡 普通] ──────── [🟢 稀疏]
  当前密度：normal（每次叙事 ≤ 300 字）

  颜色说明：
  🔴 dense  · ≤150字 ← 高压力战斗/高潮追逐（auto-switch：pressure_score ≥ 8）
  🟡 normal · ≤300字 ← 普通对话/探索（auto-switch：pressure_score 4–7）
  🟢 sparse · ≤800字 ← 长段叙事/世界观展开（auto-switch：pressure_score < 4）
```

**Auto-switch 可视化**：
- 系统检测到 `pressure_score >= 8` → 密度指示条自动滑到 🔴 并弹出 Toast：
  "战斗烈度升高，已自动切换为密集模式"
- `density_override` 被用户手动设置时：指示条锁定图标 🔒 + 提示"手动锁定"

---

## 4. 帮回快捷按钮组（Bangui Shortcut Bar）

**后端映射**：`agents/interactive.py · _BANGUI_IDS`（8个甲类帮回命令）

```
底部工具栏中央区域（帮回 8 键快捷面板）：

  帮回甲类命令：
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ 主动型1   │ │ 主动型2   │ │ 被动型1   │ │ 被动型2   │
  │ bangui_1 │ │ bangui_2 │ │ bangui_3 │ │ bangui_4 │
  └──────────┘ └──────────┘ └──────────┘ └──────────┘
  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
  │ 黑暗型1   │ │ 黑暗型2   │ │ 推进型1   │ │ 推进型2   │
  │ bangui_5 │ │ bangui_6 │ │ bangui_7 │ │ bangui_8 │
  └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

**按钮点击流**：
1. 用户点击某帮回按钮 → 调用 `InteractiveAgent.interrupt(session, bangui_cmd)`
2. 面板左边框立即变为 `#ff2e88`（INTERRUPT 状态）
3. DM 区新增一段帮回叙事（打字机展示）
4. 帮回结束后：`SessionPhase` 自动恢复 `PING_PONG`，边框颜色复原

**帮回触发视觉**：
- 被点击的帮回按钮：0.3s 内浮起 + `#ff2e88` 光晕 + 脉冲动画
- 其余 7 个按钮：临时变灰（帮回进行时禁止同时触发第二个）

---

## 5. ROLLBACK 时间回溯

**后端映射**：`InteractiveAgent.rollback(session, steps)` → 回滚 `steps` 步对话记录

### 5.1 回溯界面

点击底部 **[ROLLBACK ↩]** 按钮：

```
┌── 时间回溯选择器 ──────────────────────────────────────────────┐
│  选择回溯步数：                                                  │
│  ● 回退 1 步  ○ 回退 2 步  ○ 回退 3 步  ○ 自定义               │
│                                                                 │
│  将回退到：Turn #7（白明远踏上山脉入口之前）                      │
│                                                                 │
│  ⚠ 回退后，Turn #8–10 的历史记录将被标记"已撤销"（不删除）       │
│  [确认回退] [取消]                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 回溯后的历史记录可视化

对话历史滚动区中，被回溯的 turn 显示为：

```
Turn #8  [已撤销 × · 灰色删除线]
Turn #9  [已撤销 × · 灰色删除线]
Turn #10 [已撤销 × · 灰色删除线]
─────────────────────────────────── ← 回溯分割线（橙色虚线）
Turn #8' [当前重写 · #2ef2ff 左边框]
```

---

## 6. 滑动上下文窗口可视化（Sliding Window Monitor）

**后端映射**：`InteractiveSession.history`（已有对话轮次）+ `SessionConfig.max_turns`

```
DM 区底部滚动条区域：

  Context Window：
  [████████████░░░░░░░░░░░░░░░░░░]  已用 8 / 最大 20 turns
   ─────────────────────────────
   □ Turn 1   □ Turn 2   □ Turn 3  ...  ■ Turn 8（当前）

  窗口将于 Turn 12 触发自动压缩（MaintenanceAgent.compress_memory）
  预警（Turn 10 时）：Toast "会话上下文窗口剩余不足，将自动触发记忆压缩"
```

**窗口满载前 2 turn 触发 PACING_ALERT**：
- 面板左边框变 `#ff4040` 闪烁（`SessionPhase.PACING_ALERT`）
- Toast 警告："当前会话接近上限，建议尽快推进至着陆阶段（LANDING）"
- 底部按钮高亮 **[强制着陆 →]**

---

## 7. 着陆与章末维护

**后端映射**：`InteractiveAgent.land(session)` → `SessionPhase.LANDING` → `MAINTENANCE` → `ENDED`

```
用户点击 [结束会话] → 确认弹窗：

┌── 确认会话着陆 ────────────────────────────────────────────────┐
│  确认结束本回 TRPG 会话？系统将执行：                            │
│    1. 收束剧情（LANDING 阶段叙事生成）                           │
│    2. 更新角色状态矩阵                                          │
│    3. 压缩对话记忆至 MemorySystem（mid-layer）                  │
│    4. 提取下次钩子（next_hook）                                  │
│                                                                 │
│  [确认着陆] [继续会话]                                           │
└─────────────────────────────────────────────────────────────────┘
```

着陆动画：
- DM 区淡出打字机叙事（LANDING 段落）
- 面板左边框渐变至 `#3f5a48`（MAINTENANCE 绿色）
- 完成后显示章末总结卡：

```
┌── 会话总结 ───────────────────────────────────────────────────┐
│  会话时长：00:42    轮次：15    帮回触发：2次                    │
│  关键决策：Turn #5 [选项 B]  Turn #11 [选项 A]                  │
│  下章钩子：白明远在山脉深处听到了疑似旧友的呼救……                 │
│  角色状态更新：心理承受力 -12 / 理智值 -5                        │
│  [查看完整对话记录]  [开始新章节]  [返回标准模式]                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. TRPG UI ↔ 后端调用总览

| 用户操作 | UI 组件 | 后端方法 | 触发效果 |
|---------|---------|---------|---------|
| 进入 TRPG 模式 | 模式切换器 | `InteractiveAgent.create_session()` | 初始化 `InteractiveSession` |
| 开始会话 | 开始按钮 | `InteractiveAgent.start(session)` | `OPENING` 阶段叙事 |
| 选择/输入行动 | 玩家区按钮/输入框 | `InteractiveAgent.step(session, action)` | DM 生成回应 |
| 点击帮回按钮 | 帮回快捷栏 | `InteractiveAgent.interrupt(session, cmd)` | `INTERRUPT` 阶段 |
| 点击 ROLLBACK | 底部工具栏 | `InteractiveAgent.rollback(session, steps)` | 撤销 N 轮历史 |
| 密度手动切换 | 密度指示条锁定 | `session.density_override = "dense"` | 强制密度模式 |
| 点击结束会话 | 工具栏 / 着陆弹窗 | `InteractiveAgent.land(session)` | 着陆 → 维护 → 结束 |
