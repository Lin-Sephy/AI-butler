# Local-first 体验优化未完成方案记录（A2 已完成）

> 状态：未完成，仅记录 2026-05-26 讨论到的共识，后续需要继续校对、拆任务和验证。

## 背景问题

当前 Web App 很多交互仍然把后端请求放在用户体验的前置路径上。Render 免费后端会休眠，冷启动或网络慢时，用户会在一些本应即时响应的地方等待，例如：

- 进入聊天页时，已有本地 `session_id` 仍要等 `/api/session/{id}/messages` 返回，期间显示“正在唤醒小白”。
- 点击设置按钮后，设置页需要等待多个后端接口返回才显示内容。
- 任务完成后，数据页需要再请求 `/api/stats/dashboard` 才能拿到更新后的统计。
- 任务页、数据页、聊天页目前各自拉各自的数据，没有共享的实时前端状态。

这不代表现有设计必须保持。我们可以把前端改成 local-first：前端先响应、先显示、先更新，后端负责持久化、校准和兜底。

## 总体方向

目标不是“完全没有后端”，而是：

```text
前端：即时体验层
- 本地缓存
- 乐观更新
- 页面切换秒开
- 计时、统计、设置草稿等立即响应

后端/Edge：持久化与权威兜底层
- 保存数据库
- 调 LLM
- 记忆提取
- 任务结算校准
- 跨设备同步
```

理想体感是：用户点了就先动起来，后端慢只影响“同步中”，不阻断主要操作。

## 数据分类

### A. 可以完全本地优先

这些内容不应该等待后端：

- 当前 tab
- 聊天模式 `chat / plan`
- 当前会话 id
- 跟宠名字的展示缓存
- 设置面板输入草稿
- 人设预设文本
- 计时器显示
- 专注遮罩状态
- 折叠/展开状态
- 数据页筛选状态
- 弹窗开合状态

建议存储：React state + `localStorage`。必要时之后升级 IndexedDB。

### B. 适合本地缓存 + 后台刷新

这些内容可以先显示上次成功结果，再后台拉最新：

- 跟宠名字
- 自定义性格
- 日常作息
- 用户手记
- AI 印象展示
- LLM 配置展示状态，例如 provider/model/是否有 key
- 今日任务列表
- 最近 30 天任务列表
- 最近聊天消息
- 历史会话列表
- 数据页统计结果

建议策略：打开页面先读缓存，后台刷新成功后覆盖缓存。

### C. 可以乐观更新，但必须后台确认

这些操作可以先更新 UI，但最终以后端/数据库返回为准：

- 新建任务
- 开始任务
- 暂停/继续任务
- 完成任务
- 放弃任务
- 删除任务
- 恢复任务
- 修改任务名称
- 修改任务时长
- 保存跟宠名字
- 保存自定义性格
- 保存日常作息
- 保存用户手记
- 清空 AI 记忆
- 保存/清空 LLM 配置

建议策略：

- 前端先更新状态并标记 `sync_status: "pending"`。
- 后台请求成功后用后端返回值校准。
- 请求失败后标记 `sync_status: "failed"`，提示用户重试或回滚。

### D. 必须走后端或 Edge

这些内容不能只放前端：

- 默认 LLM API key 调用
- 聊天回复生成
- 任务模式 function calling
- AI 记忆提取
- 印象系统更新
- 使用 service role 的数据库操作
- 后端懒结算：倒计时到点自动 completed
- 正计时 8 小时封顶
- 跨天任务日刷新
- 权限校验
- 隐藏 API key 明文
- 需要避免用户篡改的权威结算逻辑

后续可以从 Render 迁到 Supabase Edge Functions 或 Cloudflare Workers，但不应直接放到浏览器。

### E. 可考虑前端直连 Supabase，但需要先配 RLS

这些内容理论上可以绕过 FastAPI，由前端通过 Supabase anon key 直接读写：

- 读取/保存用户手记
- 读取/保存日常作息
- 读取/保存 `companion_name / custom_persona`
- 读取自己的任务列表
- 创建自己的普通任务
- 更新自己的任务状态
- 读取自己的聊天记录
- 保存自己的聊天记录

前提：Supabase RLS 必须严格保证 `auth.uid() = user_id`。没有完成 RLS 校验前，不做前端直连。

## TaskStore 设想

讨论中认为最关键的架构件是一个前端共享的 `TaskStore`。

它应该负责：

- 初始化时先读本地缓存。
- 后台拉后端任务并校准。
- 维护今日任务和最近 30 天任务。
- 维护当前执行任务。
- 支持任务操作的乐观更新。
- 记录 pending/failed 同步状态。
- 提供数据页统计 selector。
- 提供聊天请求所需的任务快照。
- 记录最近发生的客户端事件。

示意：

```text
TaskStore
- tasks_today
- tasks_30d
- active_task
- recent_client_events
- sync_status by task/action

selectors
- getTodayTasks()
- getStats()
- getTaskSnapshotForChat()
- getRecentClientEventsForChat()
```

## 数据页方向

数据页不必依赖 `/api/stats/dashboard` 实时返回。

更合理的方向：

- 前端基于 TaskStore 的任务数据本地计算数据页。
- 用户完成任务后，TaskStore 立刻更新，数据页立刻重算。
- 后端 `/api/stats` 可以继续保留给小白工具 `query_stats` 使用。

数据页可在前端计算：

- 今日完成分钟数
- 今日完成任务数
- 今日 top keyword
- 日/周/月任务分布
- 24 小时专注节律
- 30 天每日分钟数
- 累计天数和累计分钟数

## 聊天与“刚刚发生的任务事件”

关键问题：如果用户刚完成任务，后端还没同步成功，就立刻去找小白，小白要能知道这件事。

讨论到的解决方向：

- 前端 TaskStore 立刻记录“刚刚完成任务”这类事件。
- 聊天请求除了用户输入，还带上 `recent_client_events` 和 `task_snapshot`。
- 后端构造给小白的上下文时，合并数据库状态和前端即时事件。

示意：

```json
{
  "recent_client_events": [
    {
      "type": "task_completed",
      "task_id": 195,
      "keyword": "学习代码",
      "minutes": 40,
      "completed_at": "...",
      "sync_status": "pending"
    }
  ],
  "task_snapshot": []
}
```

如果 `sync_status` 是 `pending`，小白可以参考，但后端和 prompt 要避免把它说成“数据库已确认”。同步成功后再变成 confirmed。

## 设置页方向

当前设置页慢，是因为打开后才请求多个接口：

- `/api/profile/companion`
- `/api/profile/daily_routine`
- `/api/memo/user`
- `/api/memo/ai`
- `/api/profile/persona_presets`
- `/api/profile/llm`

优化方向：

- 打开设置页时先显示缓存。
- 后台刷新最新设置。
- 人设预设文本可以直接打包进前端，或至少缓存。
- 保存时先更新本地缓存，再后台同步。
- 失败时提示“本地已改，保存失败，可重试”。

## 聊天页方向

当前 `ChatContext` 有 `session_id` 缓存，但消息内容仍要等后端历史接口返回。

优化方向：

- 每次收到/发送消息后，把当前会话消息写入本地缓存。
- 首次进入聊天页时先显示本地消息。
- 后台拉后端历史并合并校准。
- 发送消息仍然必须走后端/Edge，因为默认 LLM key 不能放前端。

## 任务与计时方向

已确认原则：

- 计时器显示由前端用 `started_at + Date.now()` 计算。
- 页面切走/切回不依赖 interval 持续运行。
- 后端负责权威结算：
  - 倒计时到点自动完成。
  - 正计时超过 8 小时封顶。
  - 跨天执行中的任务读取时继续可见并可处理。

进一步优化：

- 点击开始后前端先进入专注遮罩。
- 后台同步 start 请求。
- 后端返回权威 `started_at` 后校准。
- 点击完成后前端先标记 completed/pending，数据页立刻变化。

## 中国用户与浏览器兼容边界

优先使用兼容性稳定的能力：

- `fetch`
- `localStorage`
- `visibilitychange`
- `Date.now()`
- 普通 HTTPS 请求
- 普通 React state

暂不把核心体验押在：

- Web Push
- Service Worker 后台同步
- PWA 安装态
- 浏览器后台常驻
- WebSocket 长连接

原因：国内浏览器、手机省电策略、微信内置浏览器对这些能力不稳定。

## 与 Render 冷启动的关系

Render 免费后端休眠不是 bug，而是平台机制。local-first 优化的目标是：

- 让后端冷启动不阻塞大部分页面显示和基础操作。
- 把等待集中在真正必须后端参与的动作上，例如聊天回复、记忆提取、权威同步。
- 后续仍可迁移后端到 Supabase Edge Functions 或 Cloudflare Workers，但 local-first 是独立有价值的优化。

## 待确认问题

- TaskStore 用 React Context 先做，还是直接引入 Zustand 这类状态库。
- 本地缓存用 `localStorage` 先够不够，还是一开始就用 IndexedDB。
- `recent_client_events` 保留多少条、保留多久。
- pending 事件传给小白时，prompt 要如何表达，避免小白误称“已确认”。
- 前端直连 Supabase 的 RLS 规则是否已经足够安全。
- 数据页是否完全移除 `/api/stats/dashboard` 依赖，还是先保留作为后台校准。
- 设置页缓存失败/保存失败时的 UI 文案和重试入口。
- 多设备同时操作时，本地缓存和数据库冲突如何处理。

## 第一阶段建议

先不迁后端，只做低风险前端缓存与共享状态：

1. 新增本地缓存工具。
2. 设置页先读缓存、后台刷新。
3. ChatContext 先读本地消息、后台校准。
4. TaskStore 管理任务列表和任务操作乐观更新。
5. 数据页改为基于 TaskStore 本地计算。
6. 聊天请求带上 TaskStore 的即时任务上下文。

这一阶段的目标是降低等待成本，不改变数据库结构，不拆后端。
