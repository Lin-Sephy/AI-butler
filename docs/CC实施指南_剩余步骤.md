# 剩余实施步骤（给 Claude Code 的实施指南）

> **当前进度**：第 2 步已完成（v2 prompt 已替换，单次 DeepSeek 调用 + 守门校验已实现）  
> **本文档用途**：替代老版本的步骤 3-6，按新架构定义剩余工作  
> **核心参考**：CLAUDE.md 中的记忆 + 本文档。docs/ 里的 .docx 是老版本，以本文档为准。

---

## 当前架构确认

在继续之前，确认以下内容已经就绪：

- [x] DeepSeek 单次调用，返回 JSON（含 willingness / status / combo / reply / suggested_energy）
- [x] System prompt 使用意愿×状态矩阵（6 种组合 A-F）
- [x] {persona_block} 人设变量已实现
- [x] 守门校验（validate_reply）已实现
- [x] JSON 解析容错已实现
- [x] API 失败时模板兜底已实现
- [x] API 调用带最近 10 轮聊天历史（2026-03-28 完成）
- [x] 精力值动态感知 + 偏差确认面板（2026-03-28 完成）
- [x] combo A/D 按钮展示 + "换一个"追问逻辑（2026-03-28 完成）
- [x] 用户输入后立即渲染 + spinner 加载提示（2026-03-28 完成）

如果以上有未完成的，先补完再继续。

---

## 第 3 步：单任务闭环 + 按钮逻辑

**目标**：用户从收到推荐 → 启动任务 → 执行 → 暂停/完成，全流程跑通。

### 3.1 按钮展示逻辑 ✅ 已完成

AI 返回 combo 后，Python 端决定是否展示按钮：

```python
def should_show_action_buttons(ai_response):
    return ai_response.get("combo") in ["A", "D"]
```

- combo A 或 D → 回复下方展示【开始】和【换一个】两个按钮
- 其他 combo（B/C/E/F）→ 只展示回复文本，无按钮

### 3.2 "开始"按钮

用户点击"开始"：
1. 从 AI 返回的 `task_keyword` 提取任务标题（如果为 null，用回复中的建议行动作为标题）
2. 创建任务记录（task 表），status = "executing"
3. 界面进入执行状态：按钮变为「执行中(剩余X分钟) · 暂停」
4. 启动计时（时长根据精力档位设默认值：5档=90min，4档=60min，3档=30min，2档=15min，1档=不计时）

### 3.3 "换一个"按钮 ✅ 已完成

用户点击"换一个"：
1. Python 从消息池随机选一条追问，直接展示在聊天区（不调 API）：
   ```python
   FOLLOW_UP_MESSAGES = [
       "没关系，是什么让你不想做这个？",
       "好的，跟我说说你现在更想做什么？",
       "不想做就不做。你现在是累了想休息，还是想换件别的事？",
       "收到，那你现在最想做的事是什么？不管是什么都可以说。",
   ]
   ```
2. 用户回答后，这条回答作为新的 user_input，走完整的对话流程（拼 messages → 调 DeepSeek → 校验 → 展示）
3. 在 action_log 中记录：action_type = "rejected"，附带被拒绝的推荐内容

### 3.4 任务执行状态流转

```
idle → 点"开始" → executing → 点"暂停" → paused → 点"继续" → executing → 点"完成" → completed
                                                                              ↘ 点"放弃" → abandoned
```

- 暂停时：保留状态，小管家温和接住（"没关系，休息一下再说"）
- 完成时：记录 action_log，小管家正反馈（"搞定了！感觉怎么样？"）
- 放弃时：记录 action_log（pause_reason），小管家不制造愧疚感

### 3.5 完成标准

- [x] combo A/D 时展示【开始】【换一个】，其他 combo 不展示
- [ ] 点"开始"能创建任务并进入执行状态
- [x] 点"换一个"展示追问 → 用户回答 → AI 重新推荐
- [ ] 任务可暂停、继续、完成、放弃
- [ ] 所有状态转换写入 action_log

---

## 第 4 步：精力值动态感知 ✅ 已完成（2026-03-28）

**目标**：AI 每轮对话自然感知精力，偏差大时触发确认。

### 4.1 实现逻辑

```python
def check_energy_drift(ai_response, current_energy):
    suggested = ai_response.get("suggested_energy")
    if suggested is None:
        return current_energy, False
    diff = abs(suggested - current_energy)
    if diff <= 1:
        return current_energy, False
    else:
        return current_energy, True  # 需要用户确认
```

### 4.2 触发确认时的 UI

当 `needs_confirm = True`：
1. 在展示 AI 回复之前，插入一条小管家消息："你听起来状态跟之前不太一样，现在感觉怎么样？"
2. 下方展示快捷按钮：精力充沛(5) / 还行(4) / 有点累(3) / 很疲惫(2) / 完全不行(1)
3. 用户点击后更新 `st.session_state["energy_level"]` 和数据库
4. 如果精力值变了，对当前 AI 回复重新走一遍守门校验（精力值变了可能导致原本合规的推荐变违规）

### 4.3 完成标准

- [x] AI 返回的 suggested_energy 被正确解析
- [x] 偏差 ≥ 2 时弹出快捷按钮确认
- [x] 用户确认后精力值更新并持久化
- [x] 精力值变更后重新校验当前回复

---

## 第 5 步：聊天历史 + 对话上下文（部分完成）

**目标**：API 调用时传入最近 10 轮聊天历史，让 AI 有上下文。

### 5.1 实现逻辑

```python
def build_messages(system_prompt, user_input, energy_level, chat_history=None):
    messages = [{"role": "system", "content": system_prompt}]
    
    if chat_history:
        recent = chat_history[-20:]  # 10轮 = 20条消息
        messages.extend(recent)
    
    messages.append({
        "role": "user",
        "content": f"当前精力档位：{energy_level}\n用户输入：{user_input}"
    })
    
    return messages
```

### 5.2 历史记录格式

聊天历史存在 `st.session_state["chat_history"]` 中，每轮对话追加两条：
```python
# 用户消息
{"role": "user", "content": "当前精力档位：3\n用户输入：好累但是论文得写"}

# AI 回复（存 reply 文本，不存完整 JSON）
{"role": "assistant", "content": "有点累还惦记着论文，说明你还是想推进的。要不先花10分钟列个清单？"}
```

注意：存入历史的 assistant content 只放 reply 文本，不放完整 JSON。这样 AI 看到的历史是自然的对话流，不是一堆 JSON。

### 5.3 同时写入数据库

每轮对话写入 chat_session 表：
```python
{
    "user_input": "好累但是论文得写",
    "combo": "D",
    "willingness": "want",
    "status": "blocked",
    "agent_reply": "有点累还惦记着论文...",
    "energy_level": 3,
    "suggested_energy": 2,
}
```

### 5.4 完成标准

- [x] API 调用时包含最近 10 轮历史（2026-03-28 完成）
- [x] AI 回复能引用之前对话的上下文（2026-03-28 完成）
- [ ] 聊天记录写入 chat_session 表（待实现）

---

## 第 6 步：计划板 + 循环任务

**目标**：任务列表可见，循环任务每天重置。

### 6.1 计划板页面

- 展示所有任务（pending / executing / paused / completed）
- 每个任务可点击进入执行（走第 3 步的任务状态流转）
- 已完成任务灰显，可查看但不可重新启动

### 6.2 循环任务

- 支持两种 repeat_type：once（一次性）、daily（每日循环）
- 每日循环任务：每天自动重置为 pending，保留历史执行记录
- 用户可在计划板中手动添加任务（标题 + 重复类型）

### 6.3 对话中一键写入计划板

当 AI 在对话中给出了任务建议，用户点"开始"后任务自动出现在计划板中。不需要用户手动再录一次。

### 6.4 完成标准

- [ ] 计划板页面可见所有任务
- [ ] 可手动添加任务
- [ ] 每日循环任务自动重置
- [ ] 对话中启动的任务出现在计划板

---

## 第 7 步：错误处理 + 端到端测试

**目标**：所有异常不崩溃，核心流程端到端跑通。

### 7.1 错误处理清单

- [ ] DeepSeek API 超时/失败 → 模板兜底回复，不崩溃
- [ ] JSON 解析失败 → 去 markdown 标记重试，仍失败用模板
- [ ] 守门校验违规 → 情绪前缀 + 安全推荐模板
- [ ] 数据库写入失败 → 捕获异常，不影响对话
- [ ] 精力值为 null/异常 → 默认 3 档

### 7.2 端到端测试场景

跑通以下场景：

1. **combo A 全流程**：用户说"我要写论文"（精力4）→ AI 推荐任务 → 展示按钮 → 点开始 → 执行 → 完成
2. **combo D + 换一个**：用户说"好累但论文得写"（精力3）→ AI 推荐低门槛入口 → 点换一个 → 追问 → 用户回答 → 新推荐
3. **combo E 无按钮**：用户说"什么都不想做"（精力2）→ AI 接住情绪 + 恢复建议 → 无按钮
4. **守门拦截**：精力 2 档说"我要写论文" → AI 如果推荐了写论文 → 被拦截 → 模板兜底
5. **精力感知偏差**：精力显示 4 档但用户说"连续熬了三天" → suggested_energy=1 → 触发确认 → 用户确认后精力更新
6. **API 失败**：断网/超时 → 模板兜底 → 页面不崩
7. **循环任务**：添加每日任务 → 第二天自动出现

### 7.3 完成标准

- [ ] 以上 7 个场景全部跑通
- [ ] 连续使用 10 分钟无崩溃
- [ ] action_log 正确记录所有操作

---

## 第 8 步：用户记忆库（核心流程跑通后）

**目标**：用户可以录入背景信息，AI 在对话中自然使用。

### 8.1 数据库

user_profile 表新增 `user_memo` 字段（TEXT），默认为空。

### 8.2 UI

设置页面或小管家菜单中加一个文本框：
- 标题："关于你"或"让小管家更了解你"
- placeholder："比如：我是大三学生在考研 / 我下午容易犯困 / 我不喜欢小睡更喜欢散步"
- 用户随时可编辑，保存到数据库

### 8.3 Prompt 集成

user message 拼接时加入记忆：

```python
def build_user_message(user_input, energy_level, user_memo=None):
    parts = []
    if user_memo:
        parts.append(f"用户记忆档案：\n{user_memo}")
    parts.append(f"当前精力档位：{energy_level}")
    parts.append(f"用户输入：{user_input}")
    return "\n\n".join(parts)
```

system prompt 新增一句（加在回复原则末尾）：
```
- user message 中可能包含「用户记忆档案」，这是用户自己填写的背景信息。参考这些信息让你的建议更贴合用户实际情况，但不要复述这些信息。
```

### 8.4 完成标准

- [ ] 用户可以在 UI 中填写和编辑背景信息
- [ ] 填写的信息存入数据库
- [ ] AI 回复时能自然引用背景信息（如用户写了"在考研"，AI 推荐时围绕考研场景）
- [ ] AI 不会直接复述记忆内容

---

## 步骤总览

| 步骤 | 内容 | 状态 | 依赖 |
|------|------|------|------|
| 3 | 单任务闭环（按钮逻辑已完成，任务执行流转待实现） | 🔶 进行中 | 第 2 步完成 |
| 4 | 精力值动态感知 | ✅ 已完成 | 第 2 步完成 |
| 5 | 聊天历史 + 对话上下文（API 历史已完成，chat_session 写入待实现） | 🔶 进行中 | 第 2 步完成 |
| 6 | 计划板 + 循环任务 | ⬜ 待开始 | 第 3 步完成 |
| 7 | 错误处理 + 端到端测试 | ⬜ 待开始 | 全部完成 |
| 8 | 用户记忆库 | ⬜ 待开始 | 第 7 步完成 |

**下次从这里继续：** 第 3 步剩余部分（3.2 "开始"按钮创建任务 + 3.4 任务状态流转），需要实现 `core/task_manager.py`。第 5 步的 chat_session 写入可以顺手做。
