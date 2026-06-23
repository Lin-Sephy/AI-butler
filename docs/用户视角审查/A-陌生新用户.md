# A 视角：陌生新用户

> 2026-04-22 小克 review，v5 双模式 + function calling + BYOK + 白鼬 SVG 三页架构（`webapp-migration` 分支）
>
> 视角定义：一个第一次打开 app 的陌生人。已匿名登录，但没填 profile、没跟小白说过话、不知道"闲聊/任务"模式是什么。

---

## ✅ 执行记录（2026-04-22）

A 视角的 5 件事全部落地：

| # | 条目 | 改动位置 |
|---|---|---|
| 1 | TasksPage handleAction 省一次 fetch | `frontend/src/pages/TasksPage.jsx:37-49`（POST 返回值直接进 FocusOverlay，`fetchTasks` 不 await） |
| 2 | FocusOverlay 🦦 → ❄ + 白噪音整段删 | `frontend/src/components/FocusOverlay.jsx`（🦦 换雪花；"🎧 白噪音（待接入）"整段删除，等有音源再装） |
| 3 | 闲聊模式关键词触发"切任务模式"按钮 | `frontend/src/pages/ChatPage.jsx:27-35` 新增 `PLAN_INTENT_KEYWORDS`（13 词：安排/计划/改/删/取消/推到/推后/加一个/今天做/明天做/任务/待办/改一下），胶囊按钮在输入框上方条件渲染（仅闲聊+非 sending） |
| 4 | thinking 气泡动态文案 | `ChatPage.jsx:48-56` `thinkingPhase` 计时：3s 后显"在翻你任务栏..."（plan）/"在想怎么说..."（chat），8s 后换"让小白慢慢想..."，位置在白鼬下方小字 |
| 5 | App.jsx 冷启动渐进文案 | `frontend/src/App.jsx:20-36` `WAKE_MESSAGES` 三档：0-5s "正在唤醒..." / 5-15s "小白好像在睡觉，再等等..." / 15s+ "服务器刚睡醒正在洗脸..." |

未在 A 视角原清单但同轮一起做的 B-1：
- **FocusOverlay 计时器改 `Date.now()` 基准**（`FocusOverlay.jsx:7-52`）—— B 视角的最高优先级 bug（切 tab 秒数丢失），提前做了

后续追加（2026-04-22 下午，Sephy 决定）：
- **A-4 砍掉 NewTaskModal 的"专注/休息"选项**——前端入口 + `core/plan_tools.py` create_tasks schema 都清了。数据库字段和后端默认值保留（向后兼容）。详情见 `docs/死代码清理清单.md` "task_type 选项砍" 段

**测试状态**：L1 pytest 48 全过；UI 改动未在浏览器跑过，由 Sephy 手工验证（见 `docs/用户视角审查/手工测试指引.md`）。

---

## 一、Sephy 自己说出口的三个真实痛点

### ① 闲聊模式聊到任务会忘记开按钮

**现象**：用户在闲聊模式聊到"那我改一下今天的任务"，小白有时不提醒切模式，或提醒了用户也找不到在哪切。

**代码根因**：
- `prompts/system_prompt.py:70` 的 `MODE_SWITCH_HINT` 告诉 DS "顺口提一句要不要切到计划模式"——**完全靠 DS 主动记得**。
- DS 的记得力在三种情况下会衰减：历史 20 轮塞满时 attention 稀释；`custom_persona` 长时（INTJ/INFP 长预设压过这条）；聊天话题横跳时。
- 即使 DS 记得说了，**动作入口还在右上角那个 11px 的 `ModeToggle`**（`ChatPage.jsx:414`）。DS 嘴里说"要不要切"，用户眼睛得抬头到顶栏找开关。
- 语言提示和动作入口分离。

**小克倾向**：**给 ChatPage 加一个前端规则触发的小按钮**。不动 DS，不动 prompt。前端本地对用户每次发送的消息做关键词扫描（"安排 / 计划 / 改 / 删 / 取消 / 推到 / 加一个 / 今天做 / 任务"），撞上就在输入框上方贴一个"切到任务模式 →"胶囊按钮。闲聊模式才出现，已经在 plan 就隐藏。

**为什么这么修**：DS 的语义是软的（不知道用户要不要真动任务），前端规则是硬的（用户打出"删掉/取消"这种词时确定有动作意图）。两者互补，不冲突。也符合 v5 "DS 主导、Python 辅助" 的走向。

---

### ② 页面刷新有点慢

**拆三层看哪层能救：**

| 慢的来源 | 代码位置 | 能不能救 |
|---|---|---|
| a) Render free tier 14 min sleep 冷启 30s | 外部 | 救不了，但**文案能救体感** |
| b) AuthContext 必须等 Supabase signInAnonymously 才出 UI | `AuthContext.jsx:45` | 能改，收益小 |
| c) TasksPage `handleAction('start')` **连续调两次** `/api/tasks/today` | `TasksPage.jsx:41-43` | **白赚** |
| d) 切回 tasks tab 不主动刷新 | `TasksPage.jsx:27` 只在 mount 跑 | 能救，backlog 里有 |

**c) 是真正的白赚修复**。现在开始一个任务会：
```
POST /api/task/{id}/start         （写库）
GET  /api/tasks/today              ← fetchTasks()
GET  /api/tasks/today              ← 行 42 又一次，为了找 started task
```
第二次完全没必要。`tm_start_task` 返回的 task 已经是 executing 状态，直接拿它进 FocusOverlay 就行。**省一次网络往返就是省感知延迟一次。**

**a) 文案救体感**。`App.jsx:25` 现在只有"正在唤醒小白……"一行静态文字，30 秒里不变，用户会以为挂了。改成渐进式：5 秒后"小白好像在睡觉，再等等..."，15 秒后"服务器刚睡醒正在洗脸"。等待心理学经典招，成本十行代码。

**d) tab 激活刷新**。最简方案是在 App.jsx 切到 tasks 时主动 fetch（tab key 切换时 remount，或传 isActive prop）。副作用：多一些 Supabase 请求。更稳的方案是监听 ChatContext 的 `planConfirmed / lastCreatedTasks`，从聊天产生任务时主动 invalidate 任务列表——代价是两个 Context 要通信。**先做简单方案**，跑起来再说。

---

### ③ DS API 响应时间长

**代码根因**：`core/intent.py:157` 用 `chat.completions.create(...)` 不带 `stream=True`——**非流式**。用户感知延迟 = 整个回复生成完的时间。DS V3 生成 200 字大约 3-6s；任务模式再加 1-2 轮 function calling，合计 8-15s 是常态。

**两个层面能做：**

**根本解（工作量大）：流式输出**
- 后端 `/api/chat` 改 `StreamingResponse` + OpenAI `stream=True` 迭代 chunks
- 前端 ChatContext.send 改读 ReadableStream，增量更新 `messages` 最后一条
- 工作量 4-6h
- 风险：function calling 流式更复杂（tool_calls 也要增量组装）、错误恢复、前端取消请求都要小心
- 感知延迟能从 10s 降到 1-2s

**创可贴（今天就能做）：thinking 气泡动态文案**
- `ChatPage.jsx:83` 现在只要 `sending===true` 就切 `stoatState='thinking'`
- 加一个计时：0-3s 白鼬 thinking 图 + 头上三点 / 3-8s "在翻你任务栏..."（plan）或"在想怎么说..."（chat）/ 8s+ "让小白慢慢想..."
- 成本 30 分钟，体感修复

**小克倾向**：**先做创可贴，流式放到下一个集中整段时间里做**。流式看起来简单但坑多，不值得顺手做。创可贴上线后流式可以无痛替换它。

---

## 二、A 视角额外发现（按"新用户会不会懵"排序）

### 🔥 A-1. FocusOverlay 的 🦦 不是白鼬

`FocusOverlay.jsx:138` 写死 `🦦`——这是**水獭** emoji，不是白鼬。新用户第一次专注看到右下角这个小动物会困惑"这是什么？小白不是白鼬吗？"

**小克倾向**：换中性符号（❄ / ✦）或直接空着等第 3 步真 SVG 白鼬。Unicode 没有白鼬 emoji 这条路走不通。

---

### 🔥 A-2. "🎧 白噪音（待接入）"对用户 = BUG

`FocusOverlay.jsx:126` 写"（待接入）"——对 Sephy 是提醒自己要做，**对新用户是一个明显坏了的功能**。他们不知道是开发中。

**小克倾向**：**做完之前直接藏掉**。开发中的占位不往用户脸上贴，这是产品纪律。

---

### 💡 A-3. 完成按钮无确认，错按代价大

`FocusOverlay.jsx:94-105` 的"完成"按钮是主色填充、最醒目。新用户在任务刚开始（比如专注 2 分钟）意外点到，任务直接变 completed，遮罩消失，没撤销。

**小克倾向**：**短时间保护**——开始专注 30s 内点完成，弹一个"真的完成了吗？才 30 秒"的确认。长按在手机上不直观，短时间保护对误触最有效。

---

### 💡 A-4. NewTaskModal 的"专注/休息"增加认知负担

`NewTaskModal.jsx:124` 默认 `task_type='work'`，选项里有"rest"。但 grep 过代码，`task_type` 目前只在统计归类区分，**对当前 UI 无可见差异**。新用户不知道选 rest 会发生什么，是"一个不懂意义但必须做的选择"。

**小克倾向**：**砍掉"类型"字段**。大道至简 = 不让用户理解不影响主流程的选项。等做到数据页需要 work/rest 拆分时再加回来。现在是过早复杂度。

---

## 三、A 视角没提、为什么

- **Onboarding 引导** —— progress.md 写了"冷启动不预填"是决定。加引导 ≠ 预填，但这是产品方向问题，要先讨论不是直接写代码。
- **默认 persona 为空导致陪伴感弱** —— 同上，涉及"是否让小白首次见面主动问两句"，是产品决定不是代码 bug。
- **错误 alert vs ErrorBanner 不一致** —— 存在但属美学问题，不是"新用户会懵"的问题，留 C 视角。

---

## 四、A 视角优先级建议（如果今天只改 5 件事）

1. **TasksPage handleAction 省一次 fetch**（5 分钟，白赚）
2. **FocusOverlay 的 🦦 和"白噪音待接入"**（5 分钟，视觉干净）
3. **闲聊模式前端关键词触发"切任务模式"按钮**（1-2h，Sephy 核心痛点）
4. **thinking 气泡动态文案**（30 分钟，缓解等 DS 焦虑）
5. **冷启动 App.jsx 的渐进式文案**（10 分钟）

**大工作量、要先讨论、留到后面：**
- 流式输出（根本解 DS 响应慢，4-6h）
- 完成按钮保护（要选方案）
- task_type 砍掉（要确认数据页不会马上回头要它）

---

## 五、留给后续小克的上下文

- 本文档 2026-04-22 写，当天 Sephy 的三个痛点是**真实用户反馈**，不是小克脑补。
- 下一步：B 视角（Sephy 自己这种高频老用户）和 C 视角（交互设计同行）待做。
- **不要把这份清单当必改项**。先和 Sephy 对每条的优先级和方案——她是产品负责人，清单只是小克的倾向。
