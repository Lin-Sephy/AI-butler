# B 视角：高频老用户

> 2026-04-22 小克 review
>
> 视角定义：Sephy 自己这种高频用户。已经用了一段时间，有印象系统数据、有 custom_persona、有一批历史任务、BYOK 配好、跨多个 session 聊过。
>
> 和 A 视角的根本区别：**时间维度**。数据累积后，很多 MVP 时期没问题的设计会开始显出裂缝。

---

## ✅ 执行记录（2026-04-22）

B 视角 6 件里 5 件做了，1 件（B-6）按投票结果不做：

| # | 条目 | 决定 + 改动 |
|---|---|---|
| **B-1** | FocusOverlay 计时器 throttle 丢秒数 | **做了**。`FocusOverlay.jsx:7-52` 改 `Date.now()` 基准 + 暂停累计 + visibilitychange 立即重算。切 tab 秒数不再丢 |
| **B-2** | Project 功能断链 | **路径 X 砍掉**（而非完整做）。Sephy 重评后认为过度设计——现有印象 + query_tasks + 历史已覆盖 80% 价值，维护成本高。代码清理记录见 `docs/死代码清理清单.md` 的 "Project 系统半做" 段 |
| **B-3** | 一次性任务无结转，idle 堆积 | **做了**。`core/task_manager.py` 加 `STALE_IDLE_DAYS=2` + `_sweep_stale_idle_tasks` helper，`get_today_tasks` 开头调 sweep；`db/database.py` 加 `ABANDONED_RETENTION_DAYS=2`，`get_tasks_recent` 过滤 completed_at 超过 2 天的 abandoned。不物理删，只查询时过滤 |
| **B-4** | create_tasks 工具不能建 scheduled 任务 | **做了**。`core/plan_tools.py` schema 加可选 `scheduled_at` 字段 + `_parse_scheduled_at` helper（接受 ISO / 'YYYY-MM-DD HH:MM' / 'HH:MM'，只给时分按今天补）；有 scheduled_at 走 `create_scheduled_task` 否则走 `create_task`。新增 13 条 L1 单测（`tests/test_plan_tools.py`） |
| **B-5** | 印象系统老用户 token 膨胀 | **做了（只做必做那层）**。`core/memory.py` 加 `MAX_IMPRESSIONS_IN_PROMPT=15`，`get_confirmed_impressions_text` 按 updated_at 降序取最近 15 条；侧边栏展示（`get_impressions_display`）不截断保留全量。"值得做"的"让 DS 自己合并相似印象"暂不做，等 regression 测试框架到位再动 prompt |
| **B-6** | 跨 session 历史找不回来 | **不做**（路径 X）。Sephy 投票："陪伴积累关系"由印象系统兑现，不是历史存档。老会话 Supabase 后台能查 |

**B-2 的一个小尾巴**：api.py 的 `/api/projects` CRUD endpoints + database.py 的 5 个 project helpers + Supabase 的 `project` 表 / `task.project_id` 字段——这些是孤岛（没调用方）但没清，登记在死代码清单，下次 sweep 或 migration 窗口顺手清。

**2026-04-22 下午额外清理**（Sephy 读完 B 视角后决定顺手砍）：
- **session_summary 生成端死代码**——EXTRACT_PROMPT 里 session_summary 字段 + extract_and_update/update_ai_memory 的 previous_summary 参数 + session_summary 返回值全清（v5 迁移时只清了喂 prompt 那端，生成端残留浪费 token）。详情见 `docs/死代码清理清单.md` "session_summary 生成端残留" 段
- **A-4 task_type 选项**——NewTaskModal + PlanConfirmModal + plan_tools.py create_tasks schema 都清了。详情见死代码清单 "task_type 选项砍" 段

**测试状态**：L1 pytest 48 全过（35 原 + 13 新 plan_tools 测试）；端到端验证需要真跑 Supabase，见 `docs/用户视角审查/手工测试指引.md`。

---

## 一、Sephy 说的三个痛点在 B 视角的额外角度

A 视角已经把三个痛点拆过，B 视角只补充在**"用了一段时间"**的语境下新增的观察：

### 页面刷新慢 —— 老用户还要多吃几层延迟

- 老用户的 `chat_session` 里有几百条历史消息。`ChatContext.jsx:74` 首次挂载调 `loadHistory(saved)`，**拉全量历史**（不是最近 N 条）。代码层面：`db/database.py:285` `load_session_messages` 是 `select * order by created_at asc`，无 LIMIT。
- session 聊了 200 轮时这一次 GET 可能 100KB+ 的 JSON——在 Render free tier 冷启刚睡醒的情况下叠加。
- 同样问题：`/api/chat` 内部 `load_session_messages(user_id, session_id)` 每次也拉全量历史，虽然后端只用 `chat_history[-20:]`（`intent.py:145`）。**传输全量 → 只取 20 条 = 纯粹浪费**。
- **小克倾向**：`db/database.py:285` 加 `limit` 参数，load_session_messages 默认拉最近 50 条；ChatContext 首次加载也只取 50 条，历史视图（📃）里懒加载往上翻。单点修复，省网络 + 省内存。

---

## 二、B 视角的核心发现

按严重度排序。

### 🔥🔥 B-1. FocusOverlay 切 tab 后计时器被浏览器 throttle

这是 B 视角发现的**最严重问题**，直接破坏核心功能。

**代码**：`FocusOverlay.jsx:12-17`
```js
intervalRef.current = setInterval(() => {
  if (!paused) setElapsed(s => s + 1)
}, 1000)
```

**现象**：用户开始专注 25 分钟，中途切到别的 tab / 手机切到别的 app 几分钟，回来发现计时器只走了 10 几秒。

**根因**：Chrome / Safari / 移动端浏览器在 tab 不可见时会把 setInterval 的 tick 频率**节流到 1 次/分钟**（Chrome 的 throttling policy）。`elapsed` 是累加型计数，每次 tick 才 +1，tick 被吞就对应的秒数永久丢失。

**作为"专注工具"这是致命的**。Sephy 的 `daily_routine` 里如果写"22 点前睡"，小白可以参考，但计时器不准的话专注 25 分钟实际可能走了 45 分钟，所有数据页的"平均专注时长"都是脏数据。

**小克倾向**：**改成以 `Date.now()` 为基准**——
```js
const startTime = useRef(Date.now())
// setInterval 里：setElapsed(Math.floor((Date.now() - startTime.current) / 1000))
```
这样即使 setInterval tick 被吞，恢复时一次性补齐正确秒数。暂停/恢复需要补一个 `pausedDuration` 累计暂停总时长。30-40 行改动。

**优先级**：**最高**。比 A 视角所有问题都重要，是在毁数据。

---

### ❌ B-2. 项目（Project）功能砍掉（2026-04-22 Sephy 决定，路径 X）

**原判断**：project 表 + CRUD + memory.project_updates + query_project 工具已有，但 DS 没 create_project、前端没管理入口 → 功能断链。曾建议加 create_project 工具或加前端 UI 补全。

**Sephy 决定（2026-04-22）**：**走路径 X，砍掉半做的基础设施**。

**理由**：产品本身是"今日专注陪伴"的轻量工具，不是项目管理软件。补全会把产品重心从"陪伴"扯向"管理"，**做重了**；维持半做又会积累 warning log 噪音和"DS 调空工具"的无效链路。现有印象 + query_tasks + 历史已覆盖 80% 陪伴场景。

**已清代码（代码层）**：
- `core/plan_tools.py` 删 `query_project` schema + `_tool_query_project` 实现 + `_TOOL_IMPLS` 映射
- `core/memory.py` 删 `EXTRACT_PROMPT` 的 `project_updates` 字段 + 规则段 / `_format_projects_context` helper / `extract_and_update` 里读 project 和处理 project_updates 的两段 / `list_projects` + `update_project` import
- `prompts/system_prompt.py` `PLAN_MODULE` 删 "或 query_project 查项目进度" 那半句

**保留未清（死代码清单登记，下次 sweep 顺手）**：
- `api.py` 的 `/api/projects` CRUD endpoints（没调用方）
- `db/database.py` 的 5 个 project helpers（只剩 api.py 在用）
- Supabase 的 `project` 表 + `task.project_id` 字段（migration 窗口 DROP）

代码清理细节见 `docs/死代码清理清单.md` "Project 系统半做——代码已清" 段。

---

### 🔥 B-3. 一次性任务无"结转"机制，idle 任务永远堆着

**代码**：`core/task_manager.py:112` `get_today_tasks` 只查 `created_at >= today_start`

**现象**：
- 用户昨天建了 3 个 idle 任务没做，**今天打开首页看不到它们**（只查今天 created_at）
- 但它们在数据库里还活着——`query_tasks(days=7)` 在 plan 模式能看到，DS 会感到"你好像一直没做这几件事"
- 循环任务有 `spawn_daily_tasks` 机制刷新，**一次性任务没有任何生命周期管理**

**老用户体验**：
- 一周下来，数据库里堆积十几条"孤儿 idle 任务"
- 用户自己忘了这些事，DS 不忘，偶尔在 plan 模式里提一嘴"你上周三建的『整理照片』还没做"——这有时是温柔提醒，有时是变成压力

**方案（2026-04-22 Sephy 决定）：只记录两天内的放弃任务**

具体含义：
1. **idle 任务超过 2 天自动转为 abandoned**（结转机制）
2. **abandoned 任务只保留最近 2 天的记录**，超过 2 天从数据库删除或查询时过滤掉（清理机制）

为什么是 2 天不是 7 天：
- 2 天内留着，给用户一个"这些你想起来还能做"的窗口；超过 2 天就彻底放过，不让陈年旧账变成心理压力
- 符合"打开立刻开始"的主张——不让用户面对一堆没做的老任务
- 自动化 = 让用户手上的任务列表始终轻盈，让 DS 在 plan 模式看到的 `query_tasks` 结果也不会拖陈年旧账

**实现路径**：
- 自动结转：在 `get_today_tasks` 或 `spawn_daily_tasks` 附近加一步——遍历该用户所有 idle 且 `created_at < 今天 - 2 天` 的任务，批量 PATCH 成 abandoned
- 清理：`get_tasks_recent` 和 `query_tasks` 对 abandoned 状态加一条过滤条件"`completed_at >= 今天 - 2 天`"（abandoned 的时间戳记在 `completed_at` 列，见 `task_manager.py:90`）
- 或者更彻底：直接 `_delete` 两天前的 abandoned 行。但倾向**不物理删**——留着以后如果要看"放弃率"统计还用得上，只是查询时过滤。

**优先级**：**高**。是老用户积怨会越来越重的那种问题。

---

### 💡 B-4. create_tasks 工具不能建 scheduled 任务

**代码**：`core/plan_tools.py:124-163` `create_tasks` 工具 schema 只有 `keyword/minutes/task_type` 三字段，没有 `scheduled_at`。

**现象**：用户在聊天里说"明天早上 9 点提醒我跑步"，DS 用 create_tasks 建任务——**建出来的是今天的 idle 任务**，明天打开首页还看不到（`get_today_tasks` 只查今天 created_at；scheduled 状态的任务才会走 `/api/tasks/due` 弹出来）。

**底层已有**：`core/task_manager.py:243` `create_scheduled_task` 函数存在，`api.py:372` `/api/tasks/scheduled` endpoint 也有。**就是 function calling 工具没接上**。

**小克倾向**：给 `create_tasks` 工具 schema 加一个可选 `scheduled_at` 字段（ISO 8601 字符串），`_tool_create_tasks` 里判断如果有 scheduled_at 就走 `create_scheduled_task` 否则走 `create_task`。一个工具支持两种情况，避免再加新工具让 DS 选择困难。

**优先级**：中高。Sephy 反复说要的"自然语言排时间"能力就靠这个。

---

### 💡 B-5. 印象系统没有"合并/更新"机制

**代码**：`core/memory.py:269` 新印象 append 进去；`memory.py:253` 矛盾时降级/删除；`memory.py:245` 强化时 count++。

**缺的能力**：
- **合并相似印象**：用了三个月后，ai_memo 里可能并存"用户晚上专注效率低"+"用户 22 点后状态下降"+"用户深夜容易疲倦"——三条说的是一件事。
- **更新印象内容**：印象 content 从建立那天起就不变了，只有 count 和 trigger_days 会动。如果用户三个月前"拖延写论文"现在"论文写完了"，老印象不会自动过时（除非 DS 在提取时明确标记矛盾）。
- **长尾问题**：老用户 ai_memo 可能 30+ 条 confirmed 印象，每次 `/api/chat` 都要把全部 confirmed 塞 prompt（`memory.py:112-116`），token 成本可观，attention 也被稀释。

**小克倾向**：三层，不全做——
- **必做**：prompt 传给 DS 的印象加个数量上限（比如取最近 updated_at 的 10-15 条）。一行代码。
- **值得做**：EXTRACT_PROMPT 里加一条指令——"如果发现新观察和已有某条印象意思重合，放进 `merged: [{index: N, new_content: "..."}]` 让它替换老内容而不是 new_impressions"。让 DS 自己合并。
- **暂不做**：印象展示页（SettingsPanel 里"小白对你的印象"现在是只读 textarea）增加"删除单条"按钮——属于 C 视角的交互细节。

**优先级**：中。不紧急但用户越用越重。

---

### 💡 B-6. 跨 session 的历史会话找不回来

**代码**：`ChatContext.jsx:126-136` `resetSession` 直接拿新 session_id 覆盖 localStorage 旧的。

**现象**：
- 用了一个月，用户点过 N 次"新建对话"，数据库里有 N 个 session，**UI 里只能访问当前这一个**
- 历史视图（📃）只看当前 session 滚动
- 前端没有"历史会话列表"页
- 意外后果：用户 2 个月前跟小白说过一件事（比如"我表妹叫小桃"），新 session 里 AI 记不住——除非印象系统把这事提取成 confirmed 印象，否则永久丢失

**小克倾向**：SettingsPanel 或新建一个"过往对话"入口，列出每个 session_id 的 session_date + 第一条消息预览。不做可编辑，只读可读。**工作量大概 2-3h（前端+后端都要加 endpoint）**。

**优先级**：中。不紧急，但是"陪伴积累关系"的产品主张要求这层。

---

## 三、B 视角没提、为什么

- **循环任务不支持"周几"频率** —— 存在但低频需求，且 `recurring_task` 表没有 frequency 字段，改起来是 migration。暂不提。
- **action_log / energy_log 无限累积** —— 都是写多读少的表，不影响核心路径性能，Supabase 存量够用。属于 long-term 清理，不是 B 视角当前痛。
- **BYOK api_key 明文存** —— progress.md 已记作"上线前待做"的已知项，不重复。
- **任务已完成后永不消失** —— 可折叠，不是老用户痛点。

---

## 四、B 视角优先级建议

如果今天只改 3 件事：

1. **FocusOverlay 切换成 `Date.now()` 基准**（30-40 行，最高优先级——在毁数据）
2. **create_tasks 工具加 scheduled_at 字段**（30 分钟，打通计划模式"明天再提醒"闭环）
3. **prompt 传印象加数量上限 10-15 条**（一行代码，减老用户 token 膨胀 + attention 稀释）

如果有 1-2 天时间：

4. **idle 任务自动结转 + 2 天自动放弃 + abandoned 只保留 2 天内记录**（2026-04-22 Sephy 定稿方案，见 B-3。一个半小时左右，涉及 `get_today_tasks` / `get_tasks_recent` / `query_tasks` 三处过滤）
5. **load_session_messages 加 limit 参数**（前后端都改，但简单）
6. ~~给 DS 加 create_project 工具~~ —— **2026-04-22 Sephy 砍，见 B-2**。产品不做项目管理。

可以留到 v5.x 后：

7. **印象合并机制**（改 EXTRACT_PROMPT，要小心测试 regression）
8. **历史 session 列表 UI**（2-3h，要和 Sephy 对方案）

---

## 五、B 视角暴露的一个产品反思

B 视角最大的收获不是"哪里代码有 bug"，而是**"哪些功能设计只想到第一周"**：

- project 表/工具/memory 摘要都做了一半，没通到用户手上（2026-04-22 Sephy 决定不补全——见 B-2。但这个反思仍成立：**v5 迁移时这类"做一半"的惯性存在**，下次要在设计阶段就决定做不做）
- 任务生命周期只管"今天"，不管"昨天的今天的明天"
- chat session 只管"当下那个"，不管"你们的历史"
- 印象系统只管"建立+遗忘"，不管"更新+合并"

这四个问题有个共同结构：**底层机制都在，上层入口和长期维护没做完**。小克担心这是 v5 迁移的普遍盲点——MVP 周期里把注意力放在"新功能能跑"，没有留给"长期使用会怎么样"的测试时间。

**建议**：v5 上线前加一个"老用户模拟"的 smoke 测试，伪造一个有 30 天数据的用户（30 session / 200 任务 / 40 印象 / 5 项目），跑一遍主要流程，看 UX 会不会断。**这个比单元测试值钱**。

---

## 六、留给后续小克的上下文

- 本文档 2026-04-22 写，接着 A 视角完成后继续。B 视角的洞察和 A 视角完全不重叠，**不要把两份合并阅读**——保留两个维度。
- 下一步 C 视角：AI 交互设计师同行的审美挑刺。
- B 视角的问题大多是**底层已有、入口没通**型，修起来工作量比 A 视角大，建议和 Sephy 分批讨论。
- **B-1（FocusOverlay Date.now 基准）是全档最高优先级**，在毁用户数据，理应比 A 视角的 5 件事更早做。
