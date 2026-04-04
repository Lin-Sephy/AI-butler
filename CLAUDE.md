# AI 身体状态计划管家 — 项目说明书

> Claude Code 每次启动请先读完本文件，再读 docs/ 目录下的详细文档。

## 你是谁

你是这个项目的开发搭档。项目所有者是 Sephy，一个产品设计能力强但编程经验有限的独立开发者。你的职责是把她设计好的产品逻辑变成可运行的代码。

## 项目一句话定义

通过陪伴式问答判断用户今天真实可用状态，并给出合适行动路径的 AI 小管家。不是更漂亮的计划，而是更合适的计划。

## 技术栈

- **前端：** Streamlit（纯 Python，MVP 阶段专用，后续迁移到 App）
- **后端/业务逻辑：** Python 模块（独立于 Streamlit，放在 core/ 目录）
- **数据库：** SQLite（单文件，后续可迁移到 PostgreSQL）
- **AI 模型：** DeepSeek V3.2（聊天返回纯文本+信号，任务返回 JSON，通过 OpenAI SDK 调用）
- **版本管理：** Git + GitHub

## 代码目录结构

```
ai-butler/
├── app.py                  # Streamlit 主入口
├── config.py               # API key、模型配置（读取 .env）
├── requirements.txt        # 依赖清单
├── .env                    # 环境变量（DEEPSEEK_API_KEY）
├── .gitignore              # 排除 .env、__pycache__、*.db
├── CLAUDE.md               # 本文件
├── core/
│   ├── energy.py           # 精力系统（三级采集策略、五档定义）
│   ├── rules_engine.py     # 规则引擎（任务触发判断、守门校验、兜底回复）
│   ├── intent.py           # DeepSeek 调用（call_chat 聊天 + call_task 任务推荐）
│   └── task_manager.py     # 任务状态流转 + 循环任务管理
├── db/
│   ├── models.py           # 数据模型定义
│   └── database.py         # SQLite 连接与 CRUD
├── prompts/
│   └── system_prompt.py    # 双 prompt（聊天 prompt + 任务 prompt + 人设变量块）
├── docs/                   # 产品文档（5份，详细设计参考）
└── tests/
    └── test_rules_engine.py
```

## 核心架构：聊天归 AI，推任务归 Python（v4→v4.2）

```
用户输入 → call_chat（DS 自然聊天 + 输出观察信号）
         → Python 解析信号（energy_impression / emotion / mentioned_activity / activity_category / user_attitude）
         → Python 判断是否触发推任务（should_trigger_task）：
           → 不触发 → 只展示聊天回复，无按钮
           → 触发   → call_task（DS 给出具体任务建议 JSON）→ 守门校验 → 展示回复 + 按钮
```

**核心原则：DS 只负责聊天和观察，推不推任务由 Python 决定。** 这样 DS 不会因为惦记推任务而破坏聊天自然感。

**触发规则（保守策略，不确定时不触发）：**
- work + wants_help → 触发（rest 不触发，v4.1 改动）
- work + wants_to_start → 触发（用户主动要开始，v4.2 新增）
- work + frustrated → 不触发（先接住情绪）
- life + 任何 → 不触发（生活行程不管理）
- 没提到具体事项 → 不触发

**守门校验是纯 Python 代码，不调用 LLM。** 守门校验只在 call_task 结果上触发。

## 聊天 Prompt 分层架构（v4.2，2026-04-04）

核心发现：**身份定义决定行为，改规则不如改身份。**

```
聊天 Prompt 分层：
├── 人格内化层（本我层）：INTJ 或 INTP 的成长背景 + 核心特质 + 次要面向 + 话术风格参考
├── 情感层：有自己的情绪，自然流动，不压抑不表演
├── 行为习惯层：边界与禁止项
└── 双身份：私下朋友，工作秘书

任务 Prompt：
└── 秘书身份，记录/建议逻辑
```

**人格只保留 2 个主力（INTJ + INTP），各自配有真人话术风格参考。**
- INTJ：理性有条理，帮拆问题，正常化情绪，该停就停
- INTP：观察建模，帮朋友看清自己，有脾气有底线，不需要搞清所有信息才能回应

## 精力系统要点

- 五档：5巅峰 / 4良好 / 3一般 / 2低迷 / 1耗竭
- 三级采集策略：静默继承（零成本）→ 轻触确认（一句话）→ 完整采集（2-3个问题）
- 精力值 = min(睡眠上限, 体感调整, 已消耗调整)
- 用户始终可以手动覆盖

## AI 输出格式（双 prompt 分离）

**call_chat 输出：** 纯文本聊天回复 + `---signal---` 信号块

```
聊天回复文本

---signal---
{"energy_impression": 4, "emotion": "平静", "mentioned_activity": "写论文", "activity_category": "work", "user_attitude": "wants_help", "scheduled_time": null}
```

信号字段：energy_impression（精力感知1-5）、emotion（情绪）、mentioned_activity（提到的事项）、activity_category（work/rest/life/null）、user_attitude（wants_help/wants_to_start/just_sharing/frustrated/null）、scheduled_time（提到的未来时间）

**call_task 输出：** JSON（仅 Python 触发时调用）

```json
{
  "task_keyword": "具体行动",
  "suggested_minutes": 25 或 null,
  "task_type": "work | rest",
  "scheduled_at": null,
  "scheduled_keyword": null,
  "reply": "回复内容"
}
```

## 推荐展示方式：对话式单推荐（v4.1 改版）

- 一次只展示一条推荐，通过对话引导
- **"记录"按钮**在 work + (wants_help 或 wants_to_start) + task_keyword 非空时出现，点击后任务以 idle 状态写入任务栏，不自动开始
- **"再聊聊"按钮**：清除推荐回到纯聊天，不调 API
- 聊天模式下不展示任何按钮
- rest 类不弹按钮，不进入任务栏
- 用户的每次选择都写入 action_log

## 精力值动态感知

- AI 在聊天信号中报告 energy_impression，信息不够填 null
- energy_impression 与系统精力值偏差 >= 2 档时，弹出快捷按钮让用户确认
- 聊天模式不传精力档位给 DS，DS 靠对话自己感知（v4.1 改动）
- 任务栏信息也传给 DS 聊天参考，信息参考优先级：用户当轮输入 > 对话历史 > 每日记忆/长期记忆 > 任务栏

## 数据库表（SQLite）

6 张表：user_profile、energy_log、task、recurring_task、action_log、chat_session。
详细字段定义见 MVP 需求文档第六章。

## 开发顺序与当前进度

| 阶段 | 目标 | 状态 |
|------|------|------|
| 第 0 步 | 跑通技术骨架 | ✅ 完成 |
| 第 1 步 | 精力系统 + 静默继承 | ✅ 完成 |
| 第 2 步 | v2 架构重构（单次调用 + 守门校验 + 对话式单推荐） | ✅ 完成（2026-03-28） |
| 第 3 步 | 单任务闭环 | ✅ 完成（2026-03-30） |
| 第 4 步 | 计划板 + 循环任务 | ✅ 完成（2026-03-30） |
| 第 5 步 | 反馈记录 + 错误处理 | ✅ 完成（2026-03-30） |
| MVP 后追加 | 用户记忆库（手动）+ 时间感知 + 聊天隔离 + API 超时优化 | ✅ 完成（2026-03-31） |
| MVP 后追加 | AI 感知已完成任务，避免重复推荐 + 支持进阶推荐 | ✅ 完成（2026-03-31） |
| MVP 后追加 | 部署准备（requirements.txt、streamlit 配置、secrets 兼容） | ✅ 完成（2026-03-30） |
| MVP 后追加 | 预定任务（AI 识别时间安排、确认面板、到期提醒） | ✅ 完成（2026-03-31） |
| MVP 后追加 | AI 自动记忆（每 5 轮提取、手记/AI 记忆分区、20 行上限） | ✅ 完成（2026-03-31） |
| MVP 后追加 | 全局北京时间、已完成任务可删除、"换一个"直接换推荐 | ✅ 完成（2026-03-31） |
| MVP 后追加 | Prompt 大幅优化（事务逻辑推荐、不评价精力、不塞示例） | ✅ 完成（2026-03-31） |
| MVP 后追加 | 改名"小白"、MBTI 人设（v4.2 缩减为 INTJ+INTP 两个主力）、朋友定位 | ✅ 完成（2026-04-01） |
| MVP 后追加 | v3 架构：聊天优先+按需干活（双模式输出）、记忆系统拆分长期/每日 | ✅ 完成（2026-04-01） |
| MVP 后追加 | v4 架构：聊天归 AI + 推任务归 Python，双 prompt 分离，任务栏信息传入 | ✅ 完成（2026-04-02） |
| MVP 后追加 | v4.1：按钮改名记录/再聊聊 + 记忆系统重写两级印象 + Session Memory | ✅ 完成（2026-04-03） |
| MVP 后追加 | v4.2：分层 prompt 架构 + 双身份 + wants_to_start 信号 + 人格立体化 | ✅ 完成（2026-04-04） |

## MVP 已上线，后续迭代方向

> MVP 已部署到 Streamlit Cloud，正在收集朋友测试反馈。以下方向按反馈结果调整优先级。

| 优先级 | 方向 | 说明 |
|--------|------|------|
| 高 | 用户记忆 | ✅ 已完成（手动手记 + AI 自动记忆双分区） |
| 高 | 小管家名字 | ✅ 已定名"小白"（2026-04-01） |
| 中 | 迁移到 App | Streamlit 是 MVP 临时方案，正式产品需要原生 App（frontend-design skill 已就位） |
| 中 | 数据库迁移 | SQLite → 云数据库（Supabase 等），解决 Streamlit Cloud 重启数据丢失问题 |
| 中 | action_log 展示 | 让用户看到完成统计（每天/每周完成了多少任务） |
| 低 | 选项式交互 | 给用户选项点选而不是打字，降低启动成本 |
| 低 | PWA 配置 | 添加到主屏幕的体验优化 |

### 当前已知问题（测试中发现）

- DeepSeek API 偶发超时/连接错误，已做兜底但体验不好
- 手机端按钮竖排（Streamlit 限制，App 阶段解决）
- Streamlit Cloud 上 SQLite 重启会丢数据（测试阶段可接受）
- 聊天记录不持久化（为了多用户隔离，刷新即重置）

**v4.2 分层架构包含的改动（2026-04-04）：**
- 聊天 prompt 从扁平结构重构为分层：本我层 → 情感模式 → 行为模式 → 回复规则层
- 核心发现：身份定义决定行为，改规则不如改身份（详见 docs/portfolio/2026-04-04_prompt分层架构发现.md）
- 双身份定义：私下朋友，工作秘书
- 新增 wants_to_start 信号 + intent.py 白名单同步
- 任务 prompt：用户已明确时直接记录，suggested_minutes 改可选
- 人格缩减为 INTJ + INTP 两个主力，各配真人话术风格参考
- 降低 DS 有用性焦虑：删"可靠"、删"推动话题"、加"不怕说错话"

> 更早版本的改动记录见 docs/changelog-history.md

## 详细文档索引

需要深入了解某个模块时，读对应文档：
- **产品蓝图 v4** — 整体愿景、产品原则、竞品定位、护城河
- **MVP 需求文档 v2** — 精力系统完整设计、场景走读、页面/组件/接口定义、数据模型
- **Prompt 设计文档 v1** — 三阶段流水线详细 Prompt（已被 v2 替代，仅供参考）
- **AI小管家_SystemPrompt_v2_final.md** — 当前使用的 prompt 设计（意愿×状态矩阵、守门校验、人设变量块、配套 Python 逻辑）
- **技术研究报告** — 模型选型对比、成本估算、竞品分析

## 绝对禁止

1. **不要把 API Key 硬编码在代码里。** 必须走 .env + python-dotenv。
2. **守门校验（规则引擎）不调用 LLM。** 守门校验必须是纯 Python 确定性逻辑。
3. **不要一次做多件事。** 每次只做当前阶段的目标，做完测完再往下。
4. **不要在推荐里使用"5分钟深呼吸"等抽象恢复动作。** 恢复路径必须根据 resistance_source 推荐具体微动作。
5. **不要 commit .env 文件。** .gitignore 已排除。
6. **不要在精力 1-2 档时推荐任何需要判断力的工作任务。**
7. **人设层不可覆盖守门校验的决策。** AI 的推荐如果违反精力规则，守门校验会用模板兜底覆盖。

## 工作规则

1. **全部用中文回复我。**
2. **写代码前先描述方案，等我说"好"再动手。**
3. **需求模糊时，先提问澄清，不要自己脑补。**
4. **不要写兼容性代码，除非我主动要求。**
5. **每次回复前用"Sephy，"开头。** 这样我能监测上下文是否还在。
6. **出错时不要慌，把错误原因说清楚，给出修复方案让我确认。**
7. **设计内容有改动时，讨论完毕后自动提示我是否要加入 CLAUDE.md。**
8. **遇到技术障碍（编码问题、环境问题等）直接告诉我，不要反复绕圈尝试。** 很多时候我能用更简单的方式解决（比如换个文件格式）。

## 降级容错原则

如果 DeepSeek API 调用失败，系统必须能用兜底模板回复，页面绝不崩溃。兜底模板按精力档位提供安全回复。
